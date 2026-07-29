from __future__ import annotations

import logging
import threading

from .collector import CollectorError, collect
from .collector.cities import city_name
from .db import session_scope
from .models import Lead, Run, User, utcnow
from .quotas import consume

log = logging.getLogger(__name__)

_running: set[int] = set()
_lock = threading.Lock()

def is_running(run_id: int) -> bool:
    with _lock:
        return run_id in _running

def _set_stage(run_id: int, stage: str) -> None:
    with session_scope() as db:
        run = db.get(Run, run_id)
        if run:
            run.stage = stage[:200]

def _worker(run_id: int) -> None:
    try:
        with session_scope() as db:
            run = db.get(Run, run_id)
            if not run:
                return
            city_slug, niche = run.city_slug, run.niche
            limit, hot_only = run.requested, run.hot_only
            user_id = run.user_id
            run.status = "running"
            run.stage = "Запускаю браузер…"

        leads, total = collect(
            city_slug, niche, limit=limit, hot_only=hot_only,
            progress=lambda msg: _set_stage(run_id, msg),
        )

        with session_scope() as db:
            run = db.get(Run, run_id)
            if not run:
                return
            for item in leads:
                lead = Lead(
                    run_id=run.id,
                    org_id=item["org_id"],
                    name=item.get("name") or "",
                    extension=item.get("extension") or "",
                    rubric=item.get("rubric") or "",
                    address=item.get("address") or "",
                    lat=item.get("lat"),
                    lon=item.get("lon"),
                    rating=item.get("rating"),
                    reviews_count=item.get("reviews_count") or 0,
                    email=item.get("email") or "",
                    website=item.get("website") or "",
                    instagram=item.get("instagram") or "",
                    whatsapp=item.get("whatsapp") or "",
                    telegram=item.get("telegram") or "",
                    has_site=bool(item.get("has_site")),
                    is_hot=bool(item.get("is_hot")),
                    card_scraped=bool(item.get("card_scraped")),
                )
                lead.phones = item.get("phones") or []
                db.add(lead)

            run.total_in_city = total
            run.collected = len(leads)
            run.hot_count = sum(1 for x in leads if x.get("is_hot"))
            run.status = "done"
            run.stage = ""
            run.finished_at = utcnow()

            user = db.get(User, user_id)
            if user and leads:
                consume(db, user, len(leads))

    except CollectorError as exc:
        log.warning("Сбор %s не удался: %s", run_id, exc)
        _fail(run_id, str(exc))
    except Exception as exc:
        log.exception("Сбор %s упал", run_id)
        _fail(run_id, f"Непредвиденная ошибка: {exc}")
    finally:
        with _lock:
            _running.discard(run_id)

def _fail(run_id: int, message: str) -> None:
    try:
        with session_scope() as db:
            run = db.get(Run, run_id)
            if run:
                run.status = "error"
                run.error = message[:2000]
                run.stage = ""
                run.finished_at = utcnow()
    except Exception:
        log.exception("Не смог записать ошибку сбора %s", run_id)

def start(run_id: int) -> None:
    with _lock:
        if run_id in _running:
            return
        _running.add(run_id)
    threading.Thread(target=_worker, args=(run_id,), daemon=True,
                     name=f"collect-{run_id}").start()

def create_and_start(db, user: User, city_slug: str, niche: str,
                     limit: int, hot_only: bool) -> Run:
    run = Run(
        user_id=user.id,
        city_slug=city_slug,
        city_name=city_name(city_slug),
        niche=niche.strip(),
        requested=limit,
        hot_only=hot_only,
        status="pending",
        stage="В очереди…",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    start(run.id)
    return run
