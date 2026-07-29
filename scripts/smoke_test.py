import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ["DB_URL"] = f"sqlite:///{tempfile.mkdtemp()}/smoke.db"

from fastapi.testclient import TestClient

from app.db import session_scope, init_db
from app.main import app
from app.models import Lead, Message, Run

init_db()
client = TestClient(app)
ok, fail = 0, 0

def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")

print("\n=== вход и регистрация ===")
r = client.get("/")
check("гость видит форму входа", r.status_code == 200 and "GisFind" in r.text)

r = client.post("/signup", data={"email": "t@example.com", "password": "secret1"},
                follow_redirects=False)
check("регистрация", r.status_code == 303, r.status_code)

r = client.post("/signup", data={"email": "t@example.com", "password": "secret1"})
check("дубль почты отклонён", "уже зарегистрирована" in r.text)

r = client.post("/login", data={"email": "t@example.com", "password": "wrong"})
check("неверный пароль отклонён", "Неверная почта" in r.text)

client.post("/login", data={"email": "t@example.com", "password": "secret1"})

print("\n=== страницы ===")
for path, needle in [
    ("/search", "Найти клиентов"),
    ("/contacts", "База контактов"),
    ("/lists", "Сохранённые списки"),
    ("/templates", "Шаблоны и кейсы"),
    ("/guide", "Первый клиент за 48 часов"),
    ("/billing", "Тариф и оплата"),
]:
    r = client.get(path)
    check(f"{path}", r.status_code == 200 and needle in r.text,
          f"-> {r.status_code}")

print("\n=== сбор (данные подложены вручную, без сети) ===")
with session_scope() as db:
    run = Run(user_id=1, city_slug="karaganda", city_name="Караганда",
              niche="изготовление вывесок", status="done", requested=3,
              collected=3, hot_count=2, total_in_city=102)
    db.add(run)
    db.flush()
    rid = run.id
    samples = [
        ("111", "Цех", 5.0, 82, False, "", "", "+77014820961"),
        ("222", "Dipner", 4.8, 142, True, "http://dipner.kz/", "", "+77212910222"),
        ("333", "АВГ реклама", 4.4, 22, False, "", "https://instagram.com/avgrup", "+77003307766"),
        ("444", "Полиграфия.kz", 2.5, 110, True, "http://poly.kz/", "", "+77770001122"),
    ]
    for org, name, rating, reviews, has_site, site, ig, phone in samples:
        lead = Lead(run_id=rid, org_id=org, name=name,
                    rubric="Изготовление рекламных конструкций",
                    address="ул. Тестовая, 1", rating=rating, reviews_count=reviews,
                    website=site, instagram=ig, has_site=has_site,
                    is_hot=not has_site, card_scraped=True)
        lead.phones = [phone]
        db.add(lead)

r = client.get(f"/runs/{rid}")
check("страница сбора", r.status_code == 200 and "Цех" in r.text, r.status_code)
check("горячие подсвечены", "без сайта (горячие)" in r.text)
check("кнопка WhatsApp есть", "wa.me/77014820961" in r.text)
check("сайт Dipner показан", "dipner.kz" in r.text)

r = client.get(f"/api/runs/{rid}/status")
check("API статуса", r.json()["status"] == "done", r.text[:80])

r = client.get(f"/api/runs/{rid}/phones")
check("API телефонов", len(r.json()["phones"]) == 4, r.text[:80])

r = client.get(f"/runs/{rid}/csv")
check("CSV выгружается",
      r.status_code == 200 and "Цех" in r.content.decode("utf-8-sig"), r.status_code)

print("\n=== генерация сообщений ===")
r = client.post(f"/runs/{rid}/messages", data={"angle": "auto"},
                follow_redirects=False)
check("генерация отработала", r.status_code == 303, r.status_code)

with session_scope() as db:
    msgs = db.query(Message).filter(Message.run_id == rid).all()
    texts = [m.text for m in msgs]
check("сообщение на каждый лид", len(texts) == 4, f"получено {len(texts)}")
check("тексты РАЗНЫЕ", len(set(texts)) == 4, f"уникальных {len(set(texts))}")
check("в тексте есть имя бизнеса", any("Цех" in t for t in texts))
check("Dipner не получил «нет сайта»",
      not any("Сайта нет" in t or "сайта нет" in t
              for t in texts if "Dipner" in t))

bad = next((t for t in texts if "Полиграфия.kz" in t), "")
check("плохой рейтинг не хвалим", bad and "2.5" not in bad, bad[:110])
check("плохому рейтингу не пишем «выше, чем у большинства»",
      "выше, чем у большинства" not in bad, bad[:110])

from app.messaging import generate_local
low = {"org_id": "444", "name": "Полиграфия.kz", "rating": 2.5,
       "reviews_count": 110, "has_site": True, "instagram": "",
       "rubric": "полиграфия"}
t_low = generate_local(low, "rating")
check("угол «rating» при плохом рейтинге безопасен",
      "2.5" not in t_low and "в топе" not in t_low, t_low[:110])

r = client.get(f"/runs/{rid}")
check("сообщения видны на странице", "В WhatsApp" in r.text)

print("\n=== инвариант шаблонов ===")
from app import messaging

pools = {name: pool for name, pool in vars(messaging).items()
         if name.startswith("_") and isinstance(pool, list)
         and pool and isinstance(pool[0], str)}
missing = [(name, i) for name, pool in pools.items()
           for i, tpl in enumerate(pool) if "{name}" not in tpl]
check(f"во всех шаблонах есть название компании ({len(pools)} пулов)",
      not missing, missing)

a = {"org_id": "1", "name": "Альфа", "rating": None, "reviews_count": 0,
     "has_site": False, "instagram": "https://instagram.com/a", "rubric": "потолки"}
b = {"org_id": "2", "name": "Бета", "rating": None, "reviews_count": 0,
     "has_site": False, "instagram": "https://instagram.com/b", "rubric": "потолки"}
check("слабые сигналы -> тексты всё равно разные",
      messaging.generate_local(a, "auto") != messaging.generate_local(b, "auto"))

print("\n=== списки, шаблоны, тариф ===")
client.post("/lists", data={"run_id": rid, "name": "Вывески Караганда"})
r = client.get("/lists")
check("список сохранён", "Вывески Караганда" in r.text)

client.post("/templates", data={"title": "Демо-лендинг", "url": "https://demo.kz"})
r = client.get("/templates")
check("шаблон добавлен", "Демо-лендинг" in r.text)

client.post("/profile", data={"sender_name": "Тимофей", "sender_offer": "сайты и боты"})
client.post(f"/runs/{rid}/messages", data={"angle": "no_site"})
with session_scope() as db:
    t = db.query(Message).filter(Message.run_id == rid).first().text
check("подпись подставилась", "Тимофей" in t, t[-60:])
check("ссылка на кейс подставилась", "demo.kz" in t, t[-60:])

client.post("/billing", data={"plan": "start"})
r = client.get("/billing")
check("тариф переключился", "Ваш тариф" in r.text and "Старт" in r.text)

print("\n=== доступ чужого пользователя ===")
other = TestClient(app)
other.post("/signup", data={"email": "b@example.com", "password": "secret1"})
r = other.get(f"/runs/{rid}")
check("чужой сбор не открывается", r.status_code == 404, r.status_code)
r = other.get(f"/api/runs/{rid}/phones")
check("чужие телефоны не отдаются", r.status_code == 404, r.status_code)

print(f"\n{'=' * 50}\nOK: {ok}   FAIL: {fail}")
sys.exit(1 if fail else 0)
