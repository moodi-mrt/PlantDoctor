"""Passwords, sessions, CSRF and role checks.

* Passwords: argon2id (argon2-cffi defaults, RFC 9106 low-memory profile).
* Sessions: random 256-bit token in an HttpOnly cookie; only its SHA-256 is stored server-side,
  so a database leak does not leak usable sessions. Rolling expiry; revoked on logout and on
  password change / reset.
* CSRF: double-submit — a non-HttpOnly `pd_csrf` cookie whose value must be echoed in the
  `X-CSRF-Token` header on every state-changing request made with a session cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ..config import COOKIE_SECURE, CSRF_COOKIE, SESSION_COOKIE, SESSION_DAYS
from ..db import Session, User, aware, get_session, now
from .errors import AppError

_ph = PasswordHasher()
# Dummy hash so login timing is the same whether or not the email exists.
_DUMMY = _ph.hash("not-a-real-password-" + secrets.token_hex(8))

COMMON_PASSWORDS = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop", "iloveyou12",
    "pakistan123", "pakistan786", "admin12345", "welcome123", "abc1234567", "1q2w3e4r5t", "qwerty1234",
    "letmein123", "plantdoctor", "11111111111", "0000000000", "farmer1234", "password12",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, h: str | None) -> bool:
    try:
        return _ph.verify(h or _DUMMY, pw) and h is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(h: str) -> bool:
    return _ph.check_needs_rehash(h)


def password_problems(pw: str, email: str = "", name: str = "") -> list[str]:
    p = []
    if len(pw) < 10:
        p.append("Use at least 10 characters.")
    if len(pw) > 256:
        p.append("Use at most 256 characters.")
    low = pw.lower()
    if low in COMMON_PASSWORDS or len(set(pw)) < 4:
        p.append("This password is too common or simple.")
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in low:
        p.append("Don't include your email address in the password.")
    return p


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


# ───────────────────────── sessions ─────────────────────────
def create_session(db: DBSession, user: User, request: Request, response: Response) -> Session:
    token = new_token()
    s = Session(token_hash=sha256(token), user_id=user.id, csrf_token=secrets.token_urlsafe(24),
                ip=request.client.host if request.client else None,
                user_agent=(request.headers.get("user-agent") or "")[:255],
                expires_at=now() + timedelta(days=SESSION_DAYS))
    db.add(s)
    user.last_login_at = now()
    db.commit()
    set_session_cookies(response, token, s.csrf_token)
    return s


def set_session_cookies(response: Response, token: str, csrf: str):
    age = SESSION_DAYS * 86400
    response.set_cookie(SESSION_COOKIE, token, max_age=age, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=age, httponly=False, secure=COOKIE_SECURE, samesite="lax", path="/")


def clear_session_cookies(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def revoke_all_sessions(db: DBSession, user_id: int, except_id: int | None = None):
    for s in db.scalars(select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))):
        if s.id != except_id:
            s.revoked_at = now()


def _load_session(request: Request, db: DBSession) -> Session | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 100:
        return None
    s = db.scalar(select(Session).where(Session.token_hash == sha256(token)))
    if not s or s.revoked_at or aware(s.expires_at) < now() or not s.user.is_active:
        return None
    # Rolling expiry: extend when less than half the lifetime is left.
    if aware(s.expires_at) - now() < timedelta(days=SESSION_DAYS / 2):
        s.expires_at = now() + timedelta(days=SESSION_DAYS)
        db.commit()
    return s


def _check_csrf(request: Request, s: Session):
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get("x-csrf-token", "")
    if not header or not hmac.compare_digest(header, s.csrf_token):
        raise AppError(403, "Security check failed. Please reload the page and try again.", "csrf_failed")


# ───────────────────────── dependencies ─────────────────────────
def optional_user(request: Request, db: DBSession = Depends(get_session)) -> User | None:
    s = _load_session(request, db)
    if not s:
        return None
    _check_csrf(request, s)
    request.state.user_id = s.user_id
    request.state.session_id = s.id
    return s.user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise AppError(401, "Please sign in to continue.")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "You don't have permission to do this.")
        return user
    return dep


require_admin = require_role("admin")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
