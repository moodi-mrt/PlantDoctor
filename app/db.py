"""Database engine, session and ORM models (SQLAlchemy 2.x).

Schema changes go through Alembic (alembic/versions). SQLite is used for development and
tests; PostgreSQL in Docker / production — the models avoid backend-specific types.

Curated reference data (crops, diseases, treatments, products) is authored as files under
app/knowledge/ and mirrored into tables by app.services.seed so it is both version-controlled
and queryable. Image bytes are never stored in the DB: only metadata and a storage key.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import DB_URL


def now():
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


TS = DateTime(timezone=True)
ROLES = ("farmer", "consultant", "admin")


# ───────────────────────── identity ─────────────────────────
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)   # stored lower-cased
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20), default="farmer")
    locale: Mapped[str] = mapped_column(String(10), default="en")
    location: Mapped[str | None] = mapped_column(String(120))
    prefs: Mapped[dict] = mapped_column(JSON, default=dict)          # notifications, privacy toggles
    email_verified_at: Mapped[datetime | None] = mapped_column(TS)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(TS)
    __table_args__ = (CheckConstraint("role in ('farmer','consultant','admin')", name="ck_users_role"),)


class Session(Base):
    """Server-side session. Only a SHA-256 of the cookie token is stored."""
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TS, default=now)
    expires_at: Mapped[datetime] = mapped_column(TS, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    user: Mapped[User] = relationship()


class AuthToken(Base):
    """One-time email verification / password reset tokens (hashed)."""
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(10))       # verify | reset
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(TS)
    used_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=now)


class Organization(Base):
    """Designed for the organisation / enterprise phase; no UI in the MVP."""
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    plan: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(TS, default=now)


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")   # owner | admin | member
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)


# ───────────────────────── reference data ─────────────────────────
class Crop(Base):
    __tablename__ = "crops"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    scientific: Mapped[str | None] = mapped_column(String(160))
    family: Mapped[str | None] = mapped_column(String(80))
    type: Mapped[str | None] = mapped_column(String(40))
    model_prefix: Mapped[str] = mapped_column(String(40))
    supported: Mapped[bool] = mapped_column(Boolean, default=False)   # does the active model know it?
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Disease(Base):
    __tablename__ = "diseases"
    label: Mapped[str] = mapped_column(String(120), primary_key=True)   # model class label
    crop_key: Mapped[str | None] = mapped_column(ForeignKey("crops.key"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    pathogen: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[dict] = mapped_column(JSON)          # full KB entry (symptoms, treatment, references)
    in_model: Mapped[bool] = mapped_column(Boolean, default=False)


class Treatment(Base):
    __tablename__ = "treatments"
    id: Mapped[int] = mapped_column(primary_key=True)
    disease_label: Mapped[str] = mapped_column(ForeignKey("diseases.label", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(20))   # immediate | organic | chemical | preventive
    text: Mapped[str] = mapped_column(Text)
    active_ingredient: Mapped[str | None] = mapped_column(String(160), index=True)
    resistance_group: Mapped[str | None] = mapped_column(String(40))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(160))
    active_ingredient: Mapped[str] = mapped_column(String(255), index=True)
    matches_ai: Mapped[str | None] = mapped_column(String(160), index=True)
    pack_size: Mapped[str | None] = mapped_column(String(60))
    price_pkr: Mapped[float | None] = mapped_column(Float)
    store: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(512))
    verified_on: Mapped[str] = mapped_column(String(10))


class ExternalSource(Base):
    __tablename__ = "external_sources"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str | None] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(20), default="reference")   # reference | api | marketplace | dataset
    checked: Mapped[str | None] = mapped_column(String(10))


class DatasetMeta(Base):
    __tablename__ = "datasets"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    license: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[dict] = mapped_column(JSON)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(String(20))          # disease | pest
    version: Mapped[str] = mapped_column(String(80))
    arch: Mapped[str] = mapped_column(String(40))
    artifact_path: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    n_classes: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=now)
    __table_args__ = (UniqueConstraint("task", "version"),)


# ───────────────────────── user data ─────────────────────────
class Plant(Base):
    """'My Plants': a plant / field / orchard block the user tracks over time."""
    __tablename__ = "plants"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(80))
    crop_key: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=now)


class ImageRecord(Base):
    __tablename__ = "images"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(30))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS, default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(TS)


class Diagnosis(Base):
    """One analysis. `result` keeps the full model output so a saved report renders exactly as
    it did, even after the model or knowledge base changes."""
    __tablename__ = "diagnoses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id", ondelete="SET NULL"), index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"))
    heatmap_key: Mapped[str | None] = mapped_column(String(255))
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    model_version: Mapped[str] = mapped_column(String(80))
    crop_key: Mapped[str | None] = mapped_column(String(40))
    crop_source: Mapped[str] = mapped_column(String(10), default="image")   # image | user
    label: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    plant_confidence: Mapped[float | None] = mapped_column(Float)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(JSON)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(String(20))   # correct | incorrect | unsure (user)
    review: Mapped[str | None] = mapped_column(String(20))     # admin: confirmed | mislabeled | ood
    created_at: Mapped[datetime] = mapped_column(TS, default=now)
    image: Mapped[ImageRecord | None] = relationship()
    __table_args__ = (Index("ix_diagnoses_user_created", "user_id", "created_at"),
                      Index("ix_diagnoses_label", "label"), Index("ix_diagnoses_status", "status"))


class Conversation(Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    diagnosis_id: Mapped[int | None] = mapped_column(ForeignKey("diagnoses.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(TS, default=now)
    messages: Mapped[list["Message"]] = relationship(order_by="Message.id", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "assistant_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))       # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(TS, default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(40))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=now, index=True)


class ApiCache(Base):
    __tablename__ = "api_cache"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str] = mapped_column(String(160))
    value: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(TS, default=now)
    expires_at: Mapped[datetime] = mapped_column(TS, index=True)


# ───────────────────────── engine ─────────────────────────
engine = create_engine(DB_URL, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    if DB_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    """FastAPI dependency: one transaction-scoped session per request."""
    with SessionLocal() as s:
        yield s
