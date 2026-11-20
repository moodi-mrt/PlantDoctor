"""Authentication and account endpoints (/api/v1/auth/*, /api/v1/users/me)."""
from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ...config import ADMIN_EMAILS, PUBLIC_URL, SESSION_COOKIE
from ...core import ratelimit
from ...core.errors import AppError
from ...core.security import (clear_session_cookies, create_session, current_user, hash_password,
                              needs_rehash, new_token, optional_user, password_problems, revoke_all_sessions,
                              sha256, verify_password)
from ...db import AuthToken, Diagnosis, ImageRecord, Session, User, aware, get_session, now
from ...services import audit, email
from ...services.storage import storage

router = APIRouter(tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    locale: str
    location: str | None
    prefs: dict
    email_verified: bool
    created_at: str

    @classmethod
    def of(cls, u: User) -> "UserOut":
        return cls(id=u.id, email=u.email, name=u.name, role=u.role, locale=u.locale, location=u.location,
                   prefs=u.prefs or {}, email_verified=u.email_verified_at is not None,
                   created_at=aware(u.created_at).isoformat())


def _email(v: str) -> str:
    v = v.strip().lower()
    if not EMAIL_RE.match(v) or len(v) > 254:
        raise ValueError("Enter a valid email address.")
    return v


class RegisterIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    _e = field_validator("email")(_email)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = " ".join(v.split())
        if not v:
            raise ValueError("Enter your name.")
        return v


class LoginIn(BaseModel):
    email: str
    password: str = Field(max_length=256)
    _e = field_validator("email")(_email)


class EmailIn(BaseModel):
    email: str
    _e = field_validator("email")(_email)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=100)


class ResetIn(TokenIn):
    password: str = Field(max_length=256)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class ProfileIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    locale: str | None = Field(None, pattern=r"^(en|ur)$")
    location: str | None = Field(None, max_length=120)
    prefs: dict | None = None


class DeleteIn(BaseModel):
    password: str = Field(max_length=256)


def _issue(db: DBSession, user: User, purpose: str, hours: int) -> str:
    token = new_token()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=sha256(token), expires_at=now() + timedelta(hours=hours)))
    db.commit()
    return token


def _consume(db: DBSession, token: str, purpose: str) -> User:
    t = db.scalar(select(AuthToken).where(AuthToken.token_hash == sha256(token), AuthToken.purpose == purpose))
    if not t or t.used_at or aware(t.expires_at) < now():
        raise AppError(400, "This link is invalid or has expired. Please request a new one.", "invalid_token")
    t.used_at = now()
    user = db.get(User, t.user_id)
    if not user or not user.is_active:
        raise AppError(400, "This link is invalid or has expired.", "invalid_token")
    return user


def _send_verification(db: DBSession, user: User):
    token = _issue(db, user, "verify", 48)
    email.verification_email(user.email, user.name, f"{PUBLIC_URL}/verify?token={token}")


@router.post("/auth/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request, response: Response, db: DBSession = Depends(get_session)):
    ratelimit.hit(f"register:{ratelimit.client_ip(request)}", 10, 3600)
    probs = password_problems(body.password, body.email, body.name)
    if probs:
        raise AppError(422, probs[0], "weak_password", details=[{"field": "password", "message": m} for m in probs])
    if db.scalar(select(User).where(User.email == body.email)):
        raise AppError(409, "An account with this email already exists. Try signing in.", "email_taken")
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password),
                role="admin" if body.email in ADMIN_EMAILS else "farmer")
    db.add(user)
    db.commit()
    audit.record(db, request, "user.register", user.id, "user", user.id)
    _send_verification(db, user)
    create_session(db, user, request, response)
    return UserOut.of(user)


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: DBSession = Depends(get_session)):
    ip = ratelimit.client_ip(request)
    ratelimit.hit(f"login:{ip}:{body.email}", 5, 60, "Too many sign-in attempts. Wait a minute and try again.")
    ratelimit.hit(f"login-ip:{ip}", 30, 300, "Too many sign-in attempts from this network. Try again later.")
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None) or not user.is_active:
        audit.record(db, request, "auth.login_failed", user.id if user else None, "user", user.id if user else None,
                     email_domain=body.email.split("@")[-1])
        raise AppError(401, "Email or password is incorrect.", "invalid_credentials")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    create_session(db, user, request, response)
    audit.record(db, request, "auth.login", user.id, "user", user.id)
    return UserOut.of(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, user: User | None = Depends(optional_user),
           db: DBSession = Depends(get_session)):
    sid = getattr(request.state, "session_id", None)
    if sid:
        s = db.get(Session, sid)
        s.revoked_at = now()
        db.commit()
        audit.record(db, request, "auth.logout", user.id, "user", user.id)
    clear_session_cookies(response)
    response.status_code = 204
    return response


@router.post("/auth/verify", response_model=UserOut)
def verify(body: TokenIn, request: Request, db: DBSession = Depends(get_session)):
    user = _consume(db, body.token, "verify")
    user.email_verified_at = user.email_verified_at or now()
    db.commit()
    audit.record(db, request, "user.email_verified", user.id, "user", user.id)
    return UserOut.of(user)


@router.post("/auth/resend-verification", status_code=202)
def resend(request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    ratelimit.hit(f"resend:{user.id}", 3, 3600)
    if user.email_verified_at:
        return {"status": "already_verified"}
    _send_verification(db, user)
    return {"status": "sent"}


@router.post("/auth/forgot", status_code=202)
def forgot(body: EmailIn, request: Request, db: DBSession = Depends(get_session)):
    ratelimit.hit(f"forgot:{ratelimit.client_ip(request)}", 5, 3600)
    user = db.scalar(select(User).where(User.email == body.email, User.is_active.is_(True)))
    if user:
        token = _issue(db, user, "reset", 1)
        email.reset_email(user.email, user.name, f"{PUBLIC_URL}/reset?token={token}")
        audit.record(db, request, "auth.reset_requested", user.id, "user", user.id)
    # Same answer whether or not the account exists (no account enumeration).
    return {"status": "If an account exists for that email, a reset link has been sent."}


@router.post("/auth/reset", status_code=204)
def reset(body: ResetIn, request: Request, response: Response, db: DBSession = Depends(get_session)):
    ratelimit.hit(f"reset:{ratelimit.client_ip(request)}", 10, 3600)
    user = _consume(db, body.token, "reset")
    probs = password_problems(body.password, user.email, user.name)
    if probs:
        db.rollback()
        raise AppError(422, probs[0], "weak_password")
    user.password_hash = hash_password(body.password)
    user.email_verified_at = user.email_verified_at or now()   # they proved inbox access
    revoke_all_sessions(db, user.id)
    db.commit()
    audit.record(db, request, "auth.password_reset", user.id, "user", user.id)
    clear_session_cookies(response)
    response.status_code = 204
    return response


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordIn, request: Request, response: Response, user: User = Depends(current_user),
                    db: DBSession = Depends(get_session)):
    ratelimit.hit(f"pwchange:{user.id}", 5, 300)
    if not verify_password(body.current_password, user.password_hash):
        raise AppError(400, "Your current password is incorrect.", "invalid_credentials")
    probs = password_problems(body.new_password, user.email, user.name)
    if probs:
        raise AppError(422, probs[0], "weak_password")
    user.password_hash = hash_password(body.new_password)
    revoke_all_sessions(db, user.id, except_id=getattr(request.state, "session_id", None))
    db.commit()
    audit.record(db, request, "auth.password_changed", user.id, "user", user.id)
    response.status_code = 204
    return response


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut.of(user)


@router.patch("/users/me", response_model=UserOut)
def update_me(body: ProfileIn, request: Request, user: User = Depends(current_user), db: DBSession = Depends(get_session)):
    for k in ("name", "locale", "location"):
        v = getattr(body, k)
        if v is not None:
            setattr(user, k, v.strip() if isinstance(v, str) else v)
    if body.prefs is not None:
        allowed = {"email_notifications", "weather_alerts", "share_images_for_improvement", "default_crop", "units"}
        user.prefs = {**(user.prefs or {}), **{k: v for k, v in body.prefs.items() if k in allowed}}
    db.commit()
    return UserOut.of(user)


@router.delete("/users/me", status_code=204)
def delete_me(body: DeleteIn, request: Request, response: Response, user: User = Depends(current_user),
              db: DBSession = Depends(get_session)):
    """Permanently delete the account, its diagnoses and every stored image."""
    if not verify_password(body.password, user.password_hash):
        raise AppError(400, "Password is incorrect.", "invalid_credentials")
    keys = [i.storage_key for i in db.scalars(select(ImageRecord).where(ImageRecord.owner_id == user.id))]
    keys += [d.heatmap_key for d in db.scalars(select(Diagnosis).where(Diagnosis.user_id == user.id)) if d.heatmap_key]
    uid = user.id
    db.delete(user)
    db.commit()
    for k in keys:
        try:
            storage.delete(k)
        except Exception:
            pass
    audit.record(db, request, "user.deleted", None, "user", uid, images_deleted=len(keys))
    clear_session_cookies(response)
    response.status_code = 204
    return response


@router.get("/auth/session")
def session_info(request: Request, user: User | None = Depends(optional_user)):
    """Lets the SPA know whether a session exists without a 401 in the console."""
    return {"authenticated": user is not None, "user": UserOut.of(user).model_dump() if user else None,
            "has_cookie": SESSION_COOKIE in request.cookies}
