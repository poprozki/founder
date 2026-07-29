from __future__ import annotations

import json
import logging
import random
from typing import Any, Iterable, Optional

from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

log = logging.getLogger(__name__)

ANGLES = {
    "auto":    "Авто (умный выбор)",
    "no_site": "Нет сайта — уже сделал",
    "rating":  "Через рейтинг и отзывы",
    "short":   "Короткое, по делу",
}

def _rng(seed: str) -> random.Random:
    return random.Random(f"gisfind::{seed}")

def _short_rubric(rubric: str) -> str:
    r = (rubric or "").lower()
    return r[:1].lower() + r[1:] if r else "вашей нише"

def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many

def _reviews_nom(n: int) -> str:
    return f"{n} {_plural(n, 'отзыв', 'отзыва', 'отзывов')}"

def _reviews_prep(n: int) -> str:
    return f"{n} {_plural(n, 'отзыве', 'отзывах', 'отзывах')}"

_NO_SITE = [
    "Здравствуйте! Нашёл вас в 2ГИС — {name}. {proof} А сайта не нашёл: людям, "
    "которые ищут «{rubric}» в поиске, вы просто не показываетесь. "
    "Я делаю сайты под ключ, могу собрать страницу с вашими работами и заявками "
    "прямо в WhatsApp. Скинуть пример?",

    "Добрый день! Вы {name}? Смотрел «{rubric}» по городу. {proof} "
    "Но заявки идут только с 2ГИС, потому что сайта нет. "
    "Сделаю landing за неделю: работы, цены, кнопка в WhatsApp. Показать, как это выглядит?",

    "Здравствуйте! Пишу вам напрямую — вы «{name}», верно? {proof} И при этом ни сайта, "
    "ни каталога работ. Клиент, который вас загуглит, уходит к конкуренту с сайтом. "
    "Могу закрыть это за неделю. Интересно посмотреть примеры?",

    "Здравствуйте, {name}! Я делаю сайты и WhatsApp-воронки. "
    "Вижу, вы работаете в нише «{rubric}». {proof} Сайта нет — а это самый дешёвый "
    "источник заявок после 2ГИС. Скинуть пару работ, чтобы вы оценили уровень?",
]

_NO_SITE_IG = [
    "Здравствуйте! Нашёл вас в 2ГИС — «{name}» — и зашёл в Instagram, работы отличные. "
    "Но Instagram не отдаёт заявки сам: нет каталога, нет цен, нет формы. "
    "Сделаю сайт, куда будете вести трафик из профиля. {proof} Показать пример?",

    "Добрый день, {name}! Профиль в Instagram ведёте, а сайта нет — "
    "реклама упирается в ленту, и половина клиентов отваливается. "
    "Я собираю сайты под такие ниши, как «{rubric}». {proof} Скинуть кейс?",

    "Здравствуйте, {name}! Посмотрел ваш Instagram — портфолио сильное, "
    "но человеку, который хочет посчитать заказ, идти некуда: ни цен, ни заявки. "
    "{proof} Я делаю сайты, которые это закрывают. Показать пример?",

    "Добрый день, {name}! Instagram у вас живой, а вот сайта нет — "
    "и в поиске вас не найти. {proof} Для ниши «{rubric}» сайт обычно окупается "
    "с двух-трёх заказов. Скинуть работы, чтобы вы посмотрели уровень?",
]

_HAS_SITE = [
    "Здравствуйте, {name}! Смотрел ваш сайт — сделано аккуратно. "
    "{proof} Вопрос в другом: заявки с сайта обрабатываются вручную? "
    "Я ставлю WhatsApp-воронку, которая отвечает за минуту и доводит до замера. "
    "Рассказать, как это работает?",

    "Добрый день, {name}! Сайт у вас есть, так что база закрыта. "
    "{proof} Обычно в вашей нише теряются заявки, которые приходят вечером и в выходные — "
    "бот в WhatsApp это закрывает. Показать пример такой воронки?",

    "Здравствуйте, {name}! С сайтом у вас порядок, поэтому предложу другое. "
    "{proof} В нише «{rubric}» половина клиентов пишет в WhatsApp и ждёт ответа минуты, "
    "а не часы. Я собираю воронку, которая отвечает сразу и собирает замер. Интересно?",

    "Добрый день! Вижу, вы «{name}» — сайт есть, работы показаны. {proof} "
    "Спрошу по делу: сколько заявок доходит до замера? Обычно проседает именно этот шаг, "
    "и чинится он сценарием в WhatsApp. Рассказать, как?",
]

_RATING = [
    "Здравствуйте! «{name}» — рейтинг {rating} в 2ГИС при {reviews_prep}. "
    "Для ниши «{rubric}» это сильно. Обидно только, что видят его те, кто уже открыл 2ГИС. "
    "{gap} Скинуть примеры работ?",

    "Добрый день, {name}! {reviews_nom} и рейтинг {rating} — вы явно в топе по городу. "
    "{gap} Могу показать, как это выглядит у других в вашей нише.",

    "Здравствуйте, {name}! Редко вижу {reviews_nom} при рейтинге {rating} — "
    "значит, работу делаете хорошо и клиенты возвращаются. "
    "{gap} Показать, что я имею в виду?",

    "Добрый день! Вы «{name}»? Рейтинг {rating}, {reviews_nom} — по нише вы в первой строчке. "
    "{gap} Скинуть пару примеров?",
]

_SHORT = [
    "Здравствуйте! Делаю сайты и WhatsApp-воронки. Увидел {name} в 2ГИС — {gap_short} "
    "Скинуть примеры?",

    "Добрый день! Я программист, делаю сайты под «{rubric}». Увидел вас в 2ГИС, «{name}»: "
    "{gap_short} Показать пару работ?",

    "Здравствуйте, {name}! {gap_short} Занимаюсь этим под ключ. Интересно?",
]

GOOD_RATING = 4.3

def _rating_is_good(lead: dict[str, Any]) -> bool:
    rating = lead.get("rating")
    return bool(rating) and rating >= GOOD_RATING

def _proof(lead: dict[str, Any]) -> str:
    rating, reviews = lead.get("rating"), lead.get("reviews_count") or 0

    if _rating_is_good(lead):
        if reviews >= 20:
            return (f"Рейтинг {rating} при {_reviews_prep(reviews)} — "
                    f"это выше, чем у большинства в нише.")
        return f"Рейтинг {rating} — с таким уже можно продавать дороже."

    if reviews >= 50:
        return f"{_reviews_nom(reviews)} — через вас прошло много клиентов."
    if reviews >= 10:
        return f"{_reviews_nom(reviews)} — вас регулярно находят."
    return "Судя по карточке, работаете вы давно."

def _gap(lead: dict[str, Any]) -> str:
    if not lead.get("has_site"):
        return ("Сайта у вас нет — а это значит, что весь поиск в Google и Яндексе "
                "проходит мимо. Я это закрываю: сайт под ключ за неделю.")
    return ("Сайт есть, но заявки с него, скорее всего, обрабатываются руками. "
            "Ставлю WhatsApp-воронку, которая отвечает мгновенно.")

def _gap_short(lead: dict[str, Any]) -> str:
    if not lead.get("has_site"):
        return "у вас нет сайта, а он в вашей нише окупается с двух-трёх заказов."
    return "могу добавить к сайту WhatsApp-воронку, чтобы заявки не остывали."

def _pick_pool(lead: dict[str, Any], angle: str) -> list[str]:
    has_site = bool(lead.get("has_site"))
    has_ig = bool(lead.get("instagram"))
    good = _rating_is_good(lead)

    if angle == "short":
        return _SHORT
    if angle == "rating":
        if good:
            return _RATING
        return _HAS_SITE if has_site else (_NO_SITE_IG if has_ig else _NO_SITE)
    if angle == "no_site":
        return _NO_SITE_IG if (has_ig and not has_site) else _NO_SITE

    if has_site:
        return _HAS_SITE
    if has_ig:
        return _NO_SITE_IG
    if good and (lead.get("reviews_count") or 0) >= 25:
        return _RATING
    return _NO_SITE

def _signature(user: Optional[Any]) -> str:
    if not user:
        return ""
    name = (getattr(user, "sender_name", "") or "").strip()
    return f"\n\n{name}" if name else ""

def _templates_line(templates: Iterable[Any]) -> str:
    items = [t for t in (templates or []) if getattr(t, "url", "")]
    if not items:
        return ""
    first = items[0]
    return f"\n\nВот пример работы: {first.url}"

def generate_local(lead: dict[str, Any], angle: str = "auto",
                   user: Optional[Any] = None,
                   templates: Optional[Iterable[Any]] = None) -> str:
    rnd = _rng(f"{lead.get('org_id')}|{angle}")
    pool = _pick_pool(lead, angle)
    tpl = pool[rnd.randrange(len(pool))]

    reviews = lead.get("reviews_count") or 0
    text = tpl.format(
        name=lead.get("name") or "вашей компании",
        rubric=_short_rubric(lead.get("rubric", "")),
        proof=_proof(lead),
        gap=_gap(lead),
        gap_short=_gap_short(lead),
        rating=lead.get("rating") or "высокий",
        reviews_nom=_reviews_nom(reviews),
        reviews_prep=_reviews_prep(reviews),
    )
    return (text + _templates_line(templates or []) + _signature(user)).strip()

_SYSTEM = """Ты — помощник частного разработчика из Казахстана. Он делает сайты,
лендинги и воронки в WhatsApp/Instagram, и ищет клиентов через 2ГИС.

Твоя задача — написать ПЕРВОЕ холодное сообщение в WhatsApp владельцу бизнеса.

Жёсткие правила:
- Русский язык, обращение на «вы», без канцелярита и без эмодзи.
- 2-4 предложения, максимум 400 знаков. Это WhatsApp, а не письмо.
- Начни с конкретики об ИХ бизнесе (название, рейтинг, отзывы, ниша) — так видно,
  что это не массовая рассылка.
- Если у бизнеса НЕТ сайта — это главный крючок: без сайта их не находят в поиске.
- Если сайт ЕСТЬ — не ври про его отсутствие. Заходи через воронку/бота/скорость ответа.
- Закончи лёгким вопросом («скинуть примеры?», «показать?»), а не давлением.
- Не выдумывай факты, которых нет во входных данных. Не обещай сроки и цены.
- Не пиши «Здравствуйте!» одинаково во всех сообщениях — варьируй начало.

Верни JSON: {"messages": [{"org_id": "...", "text": "..."}]} — по одному на каждый вход."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "org_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["org_id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["messages"],
    "additionalProperties": False,
}

def _lead_brief(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "org_id": str(lead.get("org_id")),
        "название": lead.get("name"),
        "ниша": lead.get("rubric"),
        "рейтинг": lead.get("rating"),
        "отзывов": lead.get("reviews_count"),
        "есть_сайт": bool(lead.get("has_site")),
        "есть_instagram": bool(lead.get("instagram")),
        "город": lead.get("city_name"),
    }

def generate_with_claude(leads: list[dict[str, Any]], angle: str = "auto",
                         user: Optional[Any] = None,
                         templates: Optional[Iterable[Any]] = None
                         ) -> Optional[dict[str, str]]:
    if not ANTHROPIC_API_KEY or not leads:
        return None

    try:
        import anthropic
    except ImportError:
        log.warning("anthropic не установлен — генерирую локально")
        return None

    angle_hint = {
        "no_site": "Всем заходи через отсутствие сайта (у кого он есть — через скорость ответа).",
        "rating":  "Всем заходи через их рейтинг и отзывы.",
        "short":   "Пиши максимально коротко: 2 предложения, до 200 знаков.",
        "auto":    "Для каждого выбери самый сильный крючок сам.",
    }.get(angle, "")

    example = ""
    tpl_list = [t for t in (templates or []) if getattr(t, "url", "")]
    if tpl_list:
        example = f"\nМожно сослаться на пример работы: {tpl_list[0].url}"

    who = ""
    if user is not None and getattr(user, "sender_offer", ""):
        who = f"\nЧто он делает: {user.sender_offer}"

    payload = json.dumps([_lead_brief(x) for x in leads], ensure_ascii=False, indent=1)
    prompt = f"{angle_hint}{who}{example}\n\nБизнесы:\n{payload}"

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8000,
            system=_SYSTEM,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        log.warning("Claude недоступен (%s) — генерирую локально", exc)
        return None

    if response.stop_reason == "refusal":
        log.warning("Claude отказался генерировать — ухожу в локальный режим")
        return None

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Claude вернул невалидный JSON — генерирую локально")
        return None

    out: dict[str, str] = {}
    for item in data.get("messages", []):
        oid, msg = str(item.get("org_id", "")), (item.get("text") or "").strip()
        if oid and msg:
            out[oid] = msg
    return out or None

def generate(leads: list[dict[str, Any]], angle: str = "auto",
             user: Optional[Any] = None,
             templates: Optional[Iterable[Any]] = None) -> list[dict[str, str]]:
    claude = generate_with_claude(leads, angle, user, templates)
    sig = _signature(user)
    tpl_line = _templates_line(templates or [])

    result = []
    for lead in leads:
        oid = str(lead.get("org_id"))
        if claude and oid in claude:
            result.append({
                "org_id": oid,
                "text": (claude[oid] + tpl_line + sig).strip(),
                "source": "claude",
            })
        else:
            result.append({
                "org_id": oid,
                "text": generate_local(lead, angle, user, templates),
                "source": "local",
            })
    return result
