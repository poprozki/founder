from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Optional

_STATE_MARKER = "initialState"

def _match_braces(text: str, start: int) -> Optional[str]:
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None

def extract_initial_state(html: str) -> Optional[dict[str, Any]]:
    idx = html.find(_STATE_MARKER)
    if idx < 0:
        return None
    brace = html.find("{", idx)
    if brace < 0:
        return None
    blob = _match_braces(html, brace)
    if not blob:
        return None

    try:
        return json.loads(blob)
    except Exception:
        pass
    try:
        unescaped = json.loads('"' + blob.replace('"', '\\"') + '"')
        return json.loads(unescaped)
    except Exception:
        return None

def branches_from_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        profiles = state["data"]["entity"]["profile"]
    except (KeyError, TypeError):
        return out

    for org_id, node in (profiles or {}).items():
        data = (node or {}).get("data") or {}
        if data.get("type") != "branch":
            continue

        name_ex = data.get("name_ex") or {}
        reviews = data.get("reviews") or {}
        rubrics = data.get("rubrics") or []
        point = data.get("point") or {}

        out[str(org_id)] = {
            "org_id": str(org_id),
            "name": name_ex.get("primary") or data.get("name") or "",
            "extension": name_ex.get("extension") or "",
            "address": data.get("address_name") or "",
            "rubric": (rubrics[0].get("name") if rubrics else "") or "",
            "rating": reviews.get("general_rating"),
            "reviews_count": reviews.get("general_review_count") or 0,
            "lat": point.get("lat"),
            "lon": point.get("lon"),
        }
    return out

_TOTAL_RE = re.compile(r"Места\s*(\d[\d\s ]*)")

def total_places(body_text: str) -> int:
    m = _TOTAL_RE.search(body_text or "")
    if not m:
        return 0
    return int(re.sub(r"\D", "", m.group(1)) or 0)

def total_from_state(state: dict[str, Any]) -> int:
    try:
        profiles = state["data"]["search"]["profile"]
    except (KeyError, TypeError):
        return 0
    for node in (profiles or {}).values():
        total = ((node or {}).get("data") or {}).get("total")
        if isinstance(total, int) and total > 0:
            return total
    return 0

_LINK_HOST_RE = re.compile(r"link\.2gis\.(?:com|ru)/[\d.]+/[0-9A-Fa-f]+/(?P<payload>[A-Za-z0-9_\-+/=]+)")

def unwrap_2gis_link(href: str) -> Optional[str]:
    if not href:
        return None
    if "link.2gis." not in href:
        return href if href.startswith("http") else None

    tail = href.split("?", 1)
    if len(tail) == 2 and tail[1].startswith("http"):
        from urllib.parse import unquote
        return unquote(tail[1]).split("&")[0]

    m = _LINK_HOST_RE.search(href)
    if not m:
        return None
    payload = m.group("payload")
    payload += "=" * (-len(payload) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            raw = decoder(payload).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            continue
        first = raw.splitlines()[0].strip() if raw.strip() else ""
        if first.startswith("http"):
            return first
    return None

_SOCIAL_PATTERNS = (
    ("instagram", re.compile(r"instagram\.com|instagr\.am", re.I)),
    ("whatsapp",  re.compile(r"(?<![\w-])wa\.me/|whatsapp\.com|api\.whatsapp", re.I)),
    ("telegram",  re.compile(r"(?<![\w-])t\.me/|telegram\.(?:me|org)", re.I)),
)

_NOT_A_SITE = re.compile(
    r"2gis|instagram|whatsapp|(?<![\w-])wa\.me/|(?<![\w-])t\.me/|telegram|"
    r"facebook|vk\.com|youtube|tiktok|linkedin|twitter|(?<![\w-])x\.com|"
    r"ok\.ru|google\.|apple\.com|onelink|yandex\.|mail\.ru|(?<![\w-])bit\.ly|"
    r"taplink|linktr\.ee",
    re.I,
)

def classify_link(url: str) -> str:
    if not url:
        return "other"
    for kind, pat in _SOCIAL_PATTERNS:
        if pat.search(url):
            return kind
    if url.startswith("http") and not _NOT_A_SITE.search(url):
        return "website"
    return "other"

_DOMAIN_RE = re.compile(r"^https?://\S+$|^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}/?$", re.I)

def _own_social(kind: str, label: str, text: str) -> bool:
    return label.strip().lower() == kind

def empty_contacts() -> dict[str, Any]:
    return {"phones": [], "email": "", "website": "",
            "instagram": "", "whatsapp": "", "telegram": ""}

def contacts_from_state(state: dict[str, Any], org_id: str) -> Optional[dict[str, Any]]:
    try:
        node = state["data"]["entity"]["profile"][str(org_id)]["data"]
    except (KeyError, TypeError):
        return None

    groups = node.get("contact_groups")
    if not isinstance(groups, list):
        return None

    result = empty_contacts()
    phones: list[str] = result["phones"]

    for group in groups:
        for contact in (group or {}).get("contacts") or []:
            ctype = str(contact.get("type") or "").lower()
            value = str(contact.get("value") or "").strip()
            url = str(contact.get("url") or "").strip()
            text = str(contact.get("text") or "").strip()

            if ctype == "phone":
                num = re.sub(r"[^\d+]", "", value or text)
                if num and num not in phones:
                    phones.append(num)
                continue

            if ctype == "email":
                if not result["email"]:
                    result["email"] = value or text
                continue

            real = url or unwrap_2gis_link(value) or value
            if not real.startswith("http"):
                continue
            kind = classify_link(real)
            if kind in ("website", "instagram", "whatsapp", "telegram") \
                    and not result[kind]:
                result[kind] = real

    return result

def org_from_state(state: dict[str, Any], org_id: str) -> Optional[dict[str, Any]]:
    try:
        node = state["data"]["entity"]["profile"][str(org_id)]["data"]
    except (KeyError, TypeError):
        return None
    name_ex = node.get("name_ex") or {}
    reviews = node.get("reviews") or {}
    rubrics = node.get("rubrics") or []
    point = node.get("point") or {}
    return {
        "org_id": str(org_id),
        "name": name_ex.get("primary") or node.get("name") or "",
        "extension": name_ex.get("extension") or "",
        "address": node.get("address_name") or "",
        "rubric": (rubrics[0].get("name") if rubrics else "") or "",
        "rating": reviews.get("general_rating"),
        "reviews_count": reviews.get("general_review_count") or 0,
        "lat": point.get("lat"),
        "lon": point.get("lon"),
    }

def contacts_from_links(links: list[dict[str, Any]]) -> dict[str, Any]:
    phones: list[str] = []
    result = {"phones": phones, "email": "", "website": "",
              "instagram": "", "whatsapp": "", "telegram": ""}

    for link in links:
        href = (link.get("href") or "").strip()
        if not href:
            continue
        label = (link.get("label") or "").strip()
        text = (link.get("text") or "").strip()

        if href.startswith("tel:"):
            num = re.sub(r"[^\d+]", "", href[4:])
            if num and num not in phones:
                phones.append(num)
            continue

        if href.startswith("mailto:"):
            if not result["email"]:
                result["email"] = href[7:].split("?")[0].strip()
            continue

        real = unwrap_2gis_link(href)
        if not real:
            continue
        kind = classify_link(real)
        if kind == "other" or result.get(kind):
            continue

        if kind in ("instagram", "whatsapp", "telegram"):
            if not _own_social(kind, label, text):
                continue
        elif kind == "website":
            if not (_DOMAIN_RE.match(label) or _DOMAIN_RE.match(text)):
                continue

        result[kind] = real

    return result
