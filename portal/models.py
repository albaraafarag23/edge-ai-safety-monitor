"""The portal's tables (one database: Neon Postgres in the cloud, SQLite for tests and local runs).

Who is who:
  overseer    the SiteSentry owner: every company, site, box and account; never footage (it isn't here at all)
  manager     runs their company's sites: adds their own staff and approves their devices
  supervisor  / viewer: sign in here to reach their site's box (step 3); nothing to change here

A Device is one passkey on one phone or laptop. It must be approved before it can sign in (Lock 1). An Invite
is a one-time link that lets a new person register their first device, already approved because the person who
made the link is the approver.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./portal.db")
    # Neon / Render hand out postgres:// or postgresql:// URLs; SQLAlchemy's async driver needs +asyncpg
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
    # asyncpg takes ssl=require, not libpq's sslmode=require (Neon's URLs carry the latter)
    return url.replace("sslmode=require", "ssl=require").replace("&channel_binding=require", "")


DATABASE_URL = _database_url()
# Supabase's "transaction pooler" (port 6543) can't keep asyncpg's prepared statements between requests
_POOLED = ":6543/" in DATABASE_URL
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True,
                             connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}
                             if _POOLED else {})
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

ROLES = ("overseer", "manager", "supervisor", "viewer")


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)    # suspended: nobody in it can sign in
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)   # lower-case
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)   # None: overseer
    # WebAuthn user handle: random, so the passkey on the device doesn't carry the database id
    handle: Mapped[bytes] = mapped_column(LargeBinary(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_sign_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSite(Base):
    """Which sites a manager, supervisor or viewer works on (a manager with none: all of the company's)."""
    __tablename__ = "user_sites"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(1024), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary(2048))
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(120))                 # "Chrome on Windows", from the browser
    status: Mapped[str] = mapped_column(String(20), default="pending")   # pending | approved | refused | revoked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)   # sha256 of the link's secret
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))   # None: made on the command line
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Challenge(Base):
    """A passkey ceremony in progress (its random challenge), so any server instance can finish it."""
    __tablename__ = "challenges"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    challenge: Mapped[bytes] = mapped_column(LargeBinary(64))
    purpose: Mapped[str] = mapped_column(String(20))   # register | signin | stepup
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Session(Base):
    """A signed-in browser. Server-side, so revoking a device or a person signs them out at once."""
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)   # last passkey check


class Box(Base):
    """A Jetson. Filled by step 3 (boxes register and check in); here so the screens can show them."""
    __tablename__ = "boxes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial: Mapped[str] = mapped_column(String(64), unique=True)
    public_key: Mapped[str | None] = mapped_column(Text)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="waiting")   # waiting | approved | blocked
    last_checkin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # added for step 3 (boxes connect): add_missing_columns() puts them on an existing table
    plugins: Mapped[list | None] = mapped_column(JSON)           # rule sets its licence allows (None: none yet)
    console_url: Mapped[str | None] = mapped_column(String(300))  # where its people sign in (it says so)
    last_seq: Mapped[int | None] = mapped_column(BigInteger)       # newest signed check-in time (no replays)
    silent_noted: Mapped[bool | None] = mapped_column(Boolean)     # "went silent" already logged


class CancelledDrive(Base):
    """A rule drive that no box may use any more (lost, stolen, replaced). Sent to every box in its licence."""
    __tablename__ = "cancelled_drives"
    serial: Mapped[str] = mapped_column(String(128), primary_key=True)   # the USB stick's serial, as on the drive
    note: Mapped[str | None] = mapped_column(String(200))
    cancelled_by: Mapped[str] = mapped_column(String(120))
    cancelled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PortalKey(Base):
    """The portal's own signing key (Ed25519): licences and one-click sign-in tokens for the boxes. Made on the
    first start. Boxes pin its public half the first time they register."""
    __tablename__ = "portal_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    private_pem: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEntry(Base):
    """The security log. Each entry carries the hash of the one before, so removing or editing an old entry
    breaks the chain from there on (audit.verify)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(254))        # name at the time, or "system", "command line"
    action: Mapped[str] = mapped_column(String(60), index=True)
    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    summary: Mapped[str] = mapped_column(Text)             # plain sentence shown in the log
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


def _add_missing_columns(conn):
    """create_all makes missing tables but never changes existing ones: add any newer columns (all nullable)."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in have:
                kind = column.type.compile(dialect=conn.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {kind}'))


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
