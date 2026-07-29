import re
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
city = sys.argv[1] if len(sys.argv) > 1 else "karaganda"
niche = sys.argv[2] if len(sys.argv) > 2 else "натяжные потолки"
limit = sys.argv[3] if len(sys.argv) > 3 else "4"

client = httpx.Client(base_url=BASE, follow_redirects=True, timeout=60)
email = f"live-{uuid.uuid4().hex[:8]}@example.com"

print(f">> регистрирую {email}")
r = client.post("/signup", data={"email": email, "password": "secret1"})
assert r.status_code == 200 and "Найти клиентов" in r.text, "регистрация не прошла"

print(f">> запускаю сбор: {niche} · {city} · {limit} шт")
r = client.post("/search", data={"city": city, "niche": niche,
                                 "limit": limit, "hot_only": ""})
run_id = re.search(r"/runs/(\d+)", str(r.url))
assert run_id, f"не получил run_id, url={r.url}"
run_id = run_id.group(1)
print(f"   run_id={run_id}")

print(">> жду завершения")
stage_seen = None
for _ in range(160):
    s = client.get(f"/api/runs/{run_id}/status").json()
    if s["stage"] and s["stage"] != stage_seen:
        stage_seen = s["stage"]
        print(f"   · {stage_seen}")
    if s["status"] in ("done", "error"):
        break
    time.sleep(3)
else:
    print("!! не дождался"); sys.exit(1)

if s["status"] == "error":
    print(f"!! ОШИБКА СБОРА: {s['error']}")
    sys.exit(1)

print(f"\n>> собрано {s['collected']}, без сайта {s['hot']}, "
      f"всего в городе ~{s['total_in_city']}")
assert s["collected"] > 0, "ноль организаций"

print(">> генерирую сообщения")
client.post(f"/runs/{run_id}/messages", data={"angle": "auto"})

html = client.get(f"/runs/{run_id}").text
msgs = re.findall(r'<div class="msg-body"[^>]*>(.*?)</div>', html, re.S)
msgs = [re.sub(r"\s+", " ", m).strip() for m in msgs]
print(f"   получено сообщений: {len(msgs)}, уникальных: {len(set(msgs))}")
for m in msgs:
    print(f"\n   {m}")

wa = len(re.findall(r"wa\.me/\d+", html))
print(f"\n>> ссылок WhatsApp на странице: {wa}")

csv = client.get(f"/runs/{run_id}/csv")
print(f">> CSV: {len(csv.content)} байт, {csv.text.count(chr(10))} строк")

assert len(msgs) == s["collected"], "сообщений меньше, чем лидов"
assert len(set(msgs)) == len(msgs), "есть одинаковые сообщения"
print("\n=== ЖИВОЙ ПРОГОН ПРОЙДЕН ===")
