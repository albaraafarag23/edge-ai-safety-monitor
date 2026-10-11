"""Database tables. Contract fields (docs/contracts.md) map 1:1 to Incident columns."""
import os
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://monitor:monitor123@localhost:5432/safety_monitor",
)

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

CONTRACT_FIELDS = ["event_id", "timestamp", "plugin_id", "camera_id", "severity", "event_type",
                   "location", "duration_seconds", "rules_violated", "snapshot_url", "clip_url", "metadata"]
STATUSES = ("open", "acknowledged", "resolved")


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[str] = mapped_column(String)
    plugin_id: Mapped[str] = mapped_column(String, index=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    location: Mapped[str] = mapped_column(String)
    duration_seconds: Mapped[float] = mapped_column(Float)
    rules_violated: Mapped[list] = mapped_column(JSONB)
    snapshot_url: Mapped[str | None] = mapped_column(String)
    clip_url: Mapped[str | None] = mapped_column(String)
    # "metadata" is reserved by SQLAlchemy, so the attribute is meta but the column is "metadata"
    meta: Mapped[dict] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # supervisor workflow (not part of the incident contract)
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    status_note: Mapped[str | None] = mapped_column(Text)
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    status_updated_by: Mapped[str | None] = mapped_column(String)  # name of who last changed it ("Omar is on it")

    @classmethod
    def from_contract(cls, payload: dict) -> "Incident":
        return cls(**{("meta" if k == "metadata" else k): payload.get(k) for k in CONTRACT_FIELDS})

    def to_dict(self, report: "Report | None" = None) -> dict:
        d = {k: getattr(self, "meta" if k == "metadata" else k) for k in CONTRACT_FIELDS}
        d["received_at"] = iso(self.created_at)
        d["status"] = self.status
        d["status_note"] = self.status_note
        d["status_updated_at"] = iso(self.status_updated_at)
        d["status_updated_by"] = self.status_updated_by
        d["report"] = report.summary() if report else None
        return d


class Report(Base):
    """The AI-generated report for one incident, posted by ai_reporting."""
    __tablename__ = "reports"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    markdown: Mapped[str] = mapped_column(Text)
    markdown_ar: Mapped[str | None] = mapped_column(Text, nullable=True)  # Arabic version (contracts v2.4)
    generated_by: Mapped[str] = mapped_column(String)   # model id, "template", or "duplicate"
    delivery: Mapped[dict] = mapped_column(JSONB)       # {"status", "recipients", "attachments", "error"}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def summary(self) -> dict:
        return {"generated_by": self.generated_by, "delivery_status": (self.delivery or {}).get("status")}

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "markdown": self.markdown, "markdown_ar": self.markdown_ar,
                "generated_by": self.generated_by,
                "delivery": self.delivery, "created_at": iso(self.created_at)}


class User(Base):
    """Someone who can sign in to the dashboard. Passwords are stored as scrypt hashes (auth.py)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)  # stored lower-case
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="supervisor")    # "admin", "supervisor" or "viewer"
    password_hash: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name, "role": self.role, "active": self.active,
                "created_at": iso(self.created_at), "last_login_at": iso(self.last_login_at)}


class RuleSetting(Base):
    """A plugin rule as changed in the console (backend/rule_settings.py). No row = the plugin's defaults."""
    __tablename__ = "rule_settings"

    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    overrides: Mapped[dict] = mapped_column(JSONB, default=dict)  # changed fields only, see RULE_SETTINGS
    changed_by: Mapped[str | None] = mapped_column(String)         # name of the user who last changed it
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ZoneSetting(Base):
    """A plugin zone redrawn in the console (backend/zone_settings.py). No row = the plugin's own polygon."""
    __tablename__ = "zone_settings"

    plugin_id: Mapped[str] = mapped_column(String, primary_key=True)
    zone_id: Mapped[str] = mapped_column(String, primary_key=True)
    polygon: Mapped[list] = mapped_column(JSONB)                   # [[x, y], ...] as fractions of the picture (0-1)
    changed_by: Mapped[str | None] = mapped_column(String)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None
