from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import Any, Callable, Optional

import httpx

from ..config import (CONCURRENCY, HEADLESS, HTTP_TIMEOUT_S, PAGE_TIMEOUT_MS,
                      RESULTS_PER_PAGE, SETTLE_MS)
from .parse import (branches_from_state, contacts_from_state, empty_contacts,
                    extract_initial_state, total_from_state, total_places)

log = logging.getLogger(__name__)
Progress = Callable[[str], None]

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
}

_HTTP_FAILS_BEFORE_FALLBACK = 3

class CollectorError(RuntimeError):
    pass

class _BrowserFetcher:

    def __init__(self, concurrency: int):
        self.concurrency = concurrency
        self._pw = None
        self._browser = None
        self._ctx = None
        self._free: Optional[asyncio.Queue] = None

    async def start(self) -> None:
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                  "--disable-dev-shm-usage"])
        self._ctx = await self._browser.new_context(
            locale="ru-RU", timezone_id="Asia/Almaty", user_agent=_UA,
            viewport={"width": 1400, "height": 900})
        await self._ctx.route(
            lambda url: bool(
                __import__("re").search(r"\.(png|jpe?g|gif|webp|woff2?|ttf|mp4)", url)),
            lambda route: asyncio.ensure_future(route.abort()))
        self._free = asyncio.Queue()
        for _ in range(self.concurrency):
            self._free.put_nowait(await self._ctx.new_page())

    async def html(self, url: str) -> Optional[str]:
        if self._free is None:
            await self.start()
        page = await self._free.get()
        try:
            await page.goto(url, wait_until="domcontentloaded",
                            timeout=PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(SETTLE_MS)
            return await page.content()
        except Exception:
            return None
        finally:
            self._free.put_nowait(page)

    async def close(self) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass

class TwoGisCollector:
    def __init__(self, progress: Optional[Progress] = None,
                 concurrency: int = CONCURRENCY):
        self.concurrency = max(1, concurrency)
        self._progress = progress or (lambda _msg: None)
        self._client: Optional[httpx.AsyncClient] = None
        self._sem: Optional[asyncio.Semaphore] = None
        self._browser: Optional[_BrowserFetcher] = None
        self._http_fails = 0
        self._http_ok = 0
        self._use_browser = False
        self._done = 0

    async def __aenter__(self) -> "TwoGisCollector":
        limits = httpx.Limits(max_connections=self.concurrency * 2,
                              max_keepalive_connections=self.concurrency)
        self._client = httpx.AsyncClient(
            headers=_HEADERS, follow_redirects=True,
            timeout=HTTP_TIMEOUT_S, limits=limits)
        self._sem = asyncio.Semaphore(self.concurrency)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
        if self._browser:
            await self._browser.close()

    async def _http_html(self, url: str) -> Optional[str]:
        async with self._sem:
            try:
                resp = await self._client.get(url)
            except httpx.HTTPError:
                return None
        if resp.status_code == 200 and "initialState" in resp.text:
            return resp.text
        return None

    async def _html(self, url: str) -> Optional[str]:
        if not self._use_browser:
            html = await self._http_html(url)
            if html:
                self._http_ok += 1
                self._http_fails = 0
                return html

            await asyncio.sleep(0.7)
            html = await self._http_html(url)
            if html:
                self._http_ok += 1
                self._http_fails = 0
                return html

            self._http_fails += 1
            enough = (self._http_ok == 0
                      or self._http_fails >= _HTTP_FAILS_BEFORE_FALLBACK)
            if not enough:
                return None
            self._use_browser = True
            self._progress("2ГИС не отдаёт страницы напрямую — включаю браузер")
            log.info("HTTP-путь недоступен, переключаюсь на Playwright")

        if self._browser is None:
            self._browser = _BrowserFetcher(self.concurrency)
        async with self._sem:
            return await self._browser.html(url)

    @staticmethod
    def _search_url(city_slug: str, query: str, page: int = 1) -> str:
        base = f"https://2gis.kz/{city_slug}/search/{urllib.parse.quote(query)}"
        return base if page <= 1 else f"{base}/page/{page}"

    async def _list_page(self, page_no: int, city_slug: str,
                         query: str) -> tuple[dict[str, dict], int]:
        html = await self._html(self._search_url(city_slug, query, page_no))
        if not html:
            return {}, 0
        state = extract_initial_state(html)
        if not state:
            return {}, 0
        branches = branches_from_state(state)
        total = (total_from_state(state) or total_places(html)) if page_no == 1 else 0
        return branches, total

    async def collect_list(self, city_slug: str, query: str, want: int,
                           known: Optional[dict[str, dict]] = None,
                           first_page: int = 1,
                           max_pages: int = 60) -> tuple[dict[str, dict], int]:
        found: dict[str, dict] = dict(known or {})
        total = 0
        page_no = first_page

        while page_no <= max_pages and len(found) < want:
            batch = list(range(page_no, min(page_no + self.concurrency, max_pages + 1)))
            results = await asyncio.gather(
                *(self._list_page(n, city_slug, query) for n in batch))
            new_count, short_page = 0, False
            for branches, page_total in results:
                total = total or page_total
                for org_id, data in branches.items():
                    if org_id not in found:
                        found[org_id] = data
                        new_count += 1
                if len(branches) < RESULTS_PER_PAGE:
                    short_page = True
            self._progress(f"Выдача: найдено {len(found)} организаций")
            page_no = batch[-1] + 1
            if new_count == 0 or short_page:
                break
        return found, total

    async def scrape_card(self, city_slug: str, org_id: str,
                          announce: str = "") -> dict[str, Any]:
        url = f"https://2gis.kz/{city_slug}/firm/{org_id}"
        html = await self._html(url)
        result = empty_contacts()
        result["ok"] = False

        if html:
            state = extract_initial_state(html)
            if state:
                contacts = contacts_from_state(state, org_id)
                if contacts is not None:
                    contacts["ok"] = True
                    result = contacts

        self._done += 1
        if announce:
            self._progress(announce.format(n=self._done))
        return result

    async def run(self, city_slug: str, query: str, limit: int = 10,
                  hot_only: bool = False) -> tuple[list[dict[str, Any]], int]:
        self._progress("Открываю выдачу 2ГИС…")
        want = limit if not hot_only else limit * 3
        listing, total = await self.collect_list(city_slug, query, want)
        if not listing:
            raise CollectorError(
                "2ГИС не вернул ни одной организации. Проверьте город и нишу.")

        leads: list[dict[str, Any]] = []
        seen: set[str] = set()
        rounds = 0
        label = f"Контакты: {{n}} из {limit}"

        while True:
            queue = [o for oid, o in listing.items() if oid not in seen]
            if not queue:
                break

            need = limit - len(leads)
            chunk = queue[: max(need * 3, need + self.concurrency)] if hot_only \
                else queue[: max(need, 1) + self.concurrency]

            results = await asyncio.gather(
                *(self.scrape_card(city_slug, o["org_id"], label) for o in chunk))

            for org, contacts in zip(chunk, results):
                seen.add(org["org_id"])
                if len(leads) >= limit:
                    continue
                website = contacts.get("website", "")
                has_site = bool(website)
                if hot_only and has_site:
                    continue
                if not contacts.get("phones") and not contacts.get("whatsapp"):
                    continue
                leads.append({
                    **org,
                    "phones": contacts.get("phones", []),
                    "email": contacts.get("email", ""),
                    "website": website,
                    "instagram": contacts.get("instagram", ""),
                    "whatsapp": contacts.get("whatsapp", ""),
                    "telegram": contacts.get("telegram", ""),
                    "has_site": has_site,
                    "is_hot": not has_site,
                    "card_scraped": contacts.get("ok", False),
                })

            if len(leads) >= limit:
                break

            before = len(listing)
            listing, _ = await self.collect_list(
                city_slug, query, before + limit * 3, known=listing,
                first_page=(before // RESULTS_PER_PAGE) + 1)
            rounds += 1
            if len(listing) == before or rounds > 15:
                break

        return leads, total

async def _collect_async(city_slug: str, query: str, limit: int, hot_only: bool,
                         progress: Optional[Progress]):
    async with TwoGisCollector(progress=progress) as collector:
        return await collector.run(city_slug, query, limit=limit, hot_only=hot_only)

def collect(city_slug: str, query: str, limit: int = 10, hot_only: bool = False,
            progress: Optional[Progress] = None) -> tuple[list[dict[str, Any]], int]:
    return asyncio.run(_collect_async(city_slug, query, limit, hot_only, progress))
