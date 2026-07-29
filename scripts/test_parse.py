import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.collector.parse import (classify_link, contacts_from_links,
                                 contacts_from_state, org_from_state,
                                 total_from_state)

ok = fail = 0

def eq(label, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  OK   {label}")
    else:
        fail += 1
        print(f"  FAIL {label}\n       получено: {got!r}\n       ожидалось: {want!r}")

print("=== classify_link ===")
eq("instagram без www", classify_link("https://instagram.com/luiza_beautyhub"), "instagram")
eq("instagram с www", classify_link("http://www.instagram.com/avgrup"), "instagram")
eq("wa.me", classify_link("https://wa.me/77029058318?text=x"), "whatsapp")
eq("api.whatsapp", classify_link("http://api.whatsapp.com/send?phone=77014820961"), "whatsapp")
eq("t.me", classify_link("https://t.me/bukva_krg"), "telegram")
eq("обычный сайт", classify_link("http://dipner.kz/"), "website")
eq("start.me — не telegram", classify_link("https://start.me/page"), "website")
eq("taplink не сайт", classify_link("http://luizabeautyhub.taplink.ws/"), "other")
eq("сам 2gis не сайт", classify_link("https://2gis.kz/karaganda/firm/123"), "other")

print("\n=== contacts_from_links: реклама конкурентов ===")
links = [
    {"href": "tel:+77029058318", "label": "+7‒702‒905‒83‒18", "text": "+7‒702‒905‒83‒18"},
    {"href": "https://link.2gis.com/4.2/AAA/" +
             "aHR0cHM6Ly9pbnN0YWdyYW0uY29tL2x1aXphX2JlYXV0eWh1Ygo=",
     "label": "Instagram", "text": "Instagram"},
    {"href": "https://link.2gis.com/4.2/BBB/" +
             "aHR0cHM6Ly93YS5tZS83NzAyOTA1ODMxOAo=",
     "label": "WhatsApp", "text": "WhatsApp"},
    {"href": "https://link.2gis.com/4.2/CCC/" +
             "aHR0cDovL3d3dy5pbnN0YWdyYW0uY29tL2ltYW5vdmFfYmVhdXR5LnNhbG9uLwo=",
     "label": None, "text": "Посмотреть Instagram"},
    {"href": "https://link.2gis.com/4.2/DDD/" +
             "aHR0cDovL2FwaS53aGF0c2FwcC5jb20vc2VuZC8/cGhvbmU9NzcwNzExMTIyMjMK",
     "label": None, "text": "Написать в WhatsApp"},
]
got = contacts_from_links(links)
eq("телефон свой", got["phones"], ["+77029058318"])
eq("instagram свой", got["instagram"], "https://instagram.com/luiza_beautyhub")
eq("whatsapp свой", got["whatsapp"], "https://wa.me/77029058318")

print("\n=== contacts_from_links: сайт ===")
site_links = [
    {"href": "https://link.2gis.com/4.2/EEE/aHR0cDovL2RpcG5lci5rei8K",
     "label": "dipner.kz", "text": "dipner.kz"},
    {"href": "https://link.2gis.com/4.2/FFF/aHR0cHM6Ly9leGFtcGxlLmt6L3Byb21vCg==",
     "label": None, "text": "Узнать подробнее"},
]
got = contacts_from_links(site_links)
eq("сайт по подписи-домену", got["website"], "http://dipner.kz/")

print("\n=== contacts_from_state: основной путь ===")
STATE = {
    "data": {
        "entity": {
            "profile": {
                "11822477302834953": {
                    "data": {
                        "type": "branch",
                        "name_ex": {"primary": "Dipner",
                                    "extension": "рекламно-производственная группа"},
                        "address_name": "улица Новосёлов, 190/1",
                        "rubrics": [{"name": "Изготовление рекламных конструкций"}],
                        "reviews": {"general_rating": 4.8, "general_review_count": 142},
                        "point": {"lat": 49.8, "lon": 73.1},
                        "contact_groups": [{
                            "contacts": [
                                {"type": "phone", "value": "+77212910222",
                                 "text": "+7 (7212) 910‒222"},
                                {"type": "phone", "value": "+77051057875",
                                 "text": "+7‒705‒105‒78‒75"},
                                {"type": "phone", "value": "+77212910222",
                                 "text": "+7 (7212) 910‒222"},
                                {"type": "website", "url": "http://dipner.kz",
                                 "text": "dipner.kz",
                                 "value": "http://link.2gis.ru/1.2/X/a/b?http://dipner.kz"},
                                {"type": "email", "value": "pavel@dipner.kz"},
                                {"type": "instagram",
                                 "value": "https://instagram.com/dipnergroup"},
                                {"type": "whatsapp",
                                 "value": "https://wa.me/77051057875?text=hi"},
                            ]
                        }],
                    }
                }
            }
        },
        "search": {"profile": {"uuid-1": {"data": {"total": 388}}}},
    }
}

got = contacts_from_state(STATE, "11822477302834953")
eq("телефоны без дублей", got["phones"], ["+77212910222", "+77051057875"])
eq("сайт из поля url", got["website"], "http://dipner.kz")
eq("email", got["email"], "pavel@dipner.kz")
eq("instagram", got["instagram"], "https://instagram.com/dipnergroup")
eq("whatsapp", got["whatsapp"], "https://wa.me/77051057875?text=hi")
eq("неизвестная организация -> None",
   contacts_from_state(STATE, "нет-такой"), None)

org = org_from_state(STATE, "11822477302834953")
eq("название", org["name"], "Dipner")
eq("рейтинг", org["rating"], 4.8)
eq("отзывов", org["reviews_count"], 142)

eq("всего в городе", total_from_state(STATE), 388)
eq("нет счётчика -> 0", total_from_state({"data": {}}), 0)

print(f"\n{'=' * 46}\nOK: {ok}   FAIL: {fail}")
sys.exit(1 if fail else 0)
