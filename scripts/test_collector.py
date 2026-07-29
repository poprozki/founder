import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.collector import collect

city = sys.argv[1] if len(sys.argv) > 1 else "karaganda"
niche = sys.argv[2] if len(sys.argv) > 2 else "изготовление вывесок"
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 6
hot = "--hot" in sys.argv

t0 = time.time()
leads, total = collect(city, niche, limit=limit, hot_only=hot,
                       progress=lambda m: print(f"   · {m}", flush=True))
dt = time.time() - t0

print(f"\n{'=' * 78}")
print(f"{niche} · {city}   всего в городе: {total}   собрано: {len(leads)}   за {dt:.0f}с")
print(f"горячих (без сайта): {sum(1 for x in leads if x['is_hot'])}/{len(leads)}")
print("=" * 78)

for x in leads:
    flag = "🔥 БЕЗ САЙТА" if x["is_hot"] else "   есть сайт"
    print(f"\n{flag}  {x['name']}  ★{x['rating']} ({x['reviews_count']} отз.)")
    print(f"   {x['rubric']} · {x['address']}")
    print(f"   тел: {', '.join(x['phones']) or '—'}")
    if x["email"]:     print(f"   email: {x['email']}")
    if x["website"]:   print(f"   сайт: {x['website']}")
    if x["instagram"]: print(f"   IG: {x['instagram']}")
    if x["whatsapp"]:  print(f"   WA: {x['whatsapp'][:70]}")
    if x["telegram"]:  print(f"   TG: {x['telegram']}")

out = pathlib.Path(__file__).parent.parent / "data" / "last_test.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n-> {out}")
