import os
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _load_env(path: pathlib.Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env(BASE_DIR / ".env")

DB_PATH = DATA_DIR / "gisfind.db"
DB_URL = os.getenv("DB_URL", f"sqlite:///{DB_PATH}")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-in-prod")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

HEADLESS = os.getenv("HEADLESS", "1") != "0"
PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "60000"))
HTTP_TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "25"))
SETTLE_MS = int(os.getenv("SETTLE_MS", "2500"))

CONCURRENCY = int(os.getenv("CONCURRENCY", "12"))

RESULTS_PER_PAGE = 12

PLANS = {
    "free":  {"title": "Без тарифа", "contacts": 10,   "price": 0,    "currency": "₽"},
    "start": {"title": "Старт",      "contacts": 450,  "price": 1490, "currency": "₽"},
    "pro":   {"title": "Про",        "contacts": 1500, "price": 3900, "currency": "₽"},
    "owner": {"title": "Владелец",   "contacts": 10_000_000, "price": 0,
              "currency": "₽", "unlimited": True, "hidden": True},
}
DEFAULT_PLAN = "free"

PUBLIC_PLANS = {k: v for k, v in PLANS.items() if not v.get("hidden")}
