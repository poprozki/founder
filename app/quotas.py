from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .config import DEFAULT_PLAN, PLANS
from .models import User, utcnow

def plan_of(user: User) -> dict:
    return PLANS.get(user.plan, PLANS[DEFAULT_PLAN])

def _period_expired(user: User) -> bool:
    start = user.period_start
    if start is None:
        return True
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    return (utcnow() - start).days >= 30

def roll_period(db: Session, user: User) -> None:
    if _period_expired(user):
        user.contacts_used = 0
        user.period_start = utcnow()
        db.commit()

def remaining(db: Session, user: User) -> int:
    roll_period(db, user)
    return max(0, plan_of(user)["contacts"] - user.contacts_used)

def consume(db: Session, user: User, n: int) -> None:
    user.contacts_used += n
    db.commit()

def clamp_request(db: Session, user: User, requested: int) -> tuple[int, str]:
    left = remaining(db, user)
    if left <= 0:
        return 0, f"Лимит тарифа «{plan_of(user)['title']}» исчерпан на этот месяц."
    if requested > left:
        return left, f"Осталось {left} контактов по тарифу — собираю столько."
    return requested, ""
