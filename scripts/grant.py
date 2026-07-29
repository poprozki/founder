import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.auth import get_by_email, hash_password
from app.config import PLANS
from app.db import init_db, session_scope
from app.models import User, utcnow

parser = argparse.ArgumentParser(description="Выдать аккаунт без лимитов")
parser.add_argument("email", nargs="?", help="почта")
parser.add_argument("password", nargs="?", help="пароль (мин. 6 символов)")
parser.add_argument("--plan", default="owner", choices=list(PLANS),
                    help="тариф, по умолчанию owner (без лимита)")
parser.add_argument("--list", action="store_true", help="показать всех пользователей")
args = parser.parse_args()

init_db()

if args.list:
    with session_scope() as db:
        users = db.scalars(select(User).order_by(User.id)).all()
        if not users:
            print("Пользователей ещё нет.")
        for u in users:
            p = PLANS.get(u.plan, {})
            limit = "без лимита" if p.get("unlimited") else f"{u.contacts_used}/{p.get('contacts', '?')}"
            print(f"  #{u.id}  {u.email:<34} {p.get('title', u.plan):<12} {limit}")
    sys.exit(0)

if not args.email:
    parser.error("укажите почту (или --list)")

plan = PLANS[args.plan]

with session_scope() as db:
    user = get_by_email(db, args.email)

    if user:
        user.plan = args.plan
        user.contacts_used = 0
        user.period_start = utcnow()
        if args.password:
            if len(args.password) < 6:
                sys.exit("Пароль — минимум 6 символов.")
            user.password_hash = hash_password(args.password)
            print(f"Пароль обновлён.")
        print(f"Аккаунт {user.email} переведён на тариф «{plan['title']}».")
    else:
        if not args.password:
            sys.exit("Для нового аккаунта нужен пароль: grant.py почта пароль")
        if len(args.password) < 6:
            sys.exit("Пароль — минимум 6 символов.")
        user = User(
            email=args.email.lower().strip(),
            password_hash=hash_password(args.password),
            plan=args.plan,
            period_start=utcnow(),
        )
        db.add(user)
        print(f"Создан аккаунт {user.email}, тариф «{plan['title']}».")

    limit = "без лимита" if plan.get("unlimited") else f"{plan['contacts']} контактов/мес"
    print(f"Лимит: {limit}")

print("\nВходите на http://127.0.0.1:8000")
