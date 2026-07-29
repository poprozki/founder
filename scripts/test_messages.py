import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.messaging import generate_local

angle = sys.argv[1] if len(sys.argv) > 1 else "auto"
leads = json.loads((pathlib.Path("data") / "last_test.json").read_text(encoding="utf-8"))

texts = []
for x in leads:
    t = generate_local(x, angle)
    texts.append(t)
    site = "да" if x["has_site"] else "НЕТ"
    ig = "да" if x["instagram"] else "нет"
    print(f"--- {x['name']}  (сайт: {site}, IG: {ig}, ★{x['rating']}, {x['reviews_count']} отз.)")
    print(t)
    print(f"[{len(t)} знаков]\n")

print(f">>> угол «{angle}»: уникальных текстов {len(set(texts))} из {len(texts)}")
