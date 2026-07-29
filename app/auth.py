from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional

from fastapi import Request
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SECRET_KEY
from .models import User

COOKIE_NAME = "gisfind_session"
_ITERATIONS = 260_000
_serializer = URLSafeSerializer(SECRET_KEY, salt="gisfind-auth")

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False

def make_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})

def read_session(token: str) -> Optional[int]:
    try:
        return _serializer.loads(token).get("uid")
    except (BadSignature, AttributeError):
        return None

def current_user(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    uid = read_session(token)
    if uid is None:
        return None
    return db.get(User, uid)

def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email.lower().strip()))

def create_user(db: Session, email: str, password: str) -> User:
    user = User(email=email.lower().strip(), password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
