import os
import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import String, DateTime, Float, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://monitor:monitor123@localhost:5432/safety_monitor",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
INCIDENT_STREAM = "incidents"
CONSUMER_GROUP = "backend"
CONSUMER_NAME = "backend_01"
# snapshots and clips written by cv_pipeline, served at /media/...
MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Incident(Base):
    """One incident payload (docs/contracts.md). Contract fields map 1:1 to columns."""
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


CONTRACT_FIELDS = ["event_id", "timestamp", "plugin_id", "camera_id", "severity", "event_type",
                   "location", "duration_seconds", "rules_violated", "snapshot_url", "clip_url", "metadata"]


class Report(Base):
    """The AI-generated report for one incident, posted by ai_reporting."""
    __tablename__ = "reports"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    markdown: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String)   # model id, or "template" if the LLM was unavailable
    delivery: Mapped[dict] = mapped_column(JSONB)       # {"status", "recipients", "attachments", "error"}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReportIn(BaseModel):
    event_id: str
    markdown: str
    generated_by: str
    delivery: dict = {}


async def consume_incidents(r: aioredis.Redis):
    try:
        await r.xgroup_create(INCIDENT_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            print(f"[Backend] xgroup_create: {e}", flush=True)

    print("[Backend] Consuming incidents stream...", flush=True)

    while True:
        try:
            messages = await r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {INCIDENT_STREAM: ">"},
                count=10,
                block=1000,
            )
            if not messages:
                continue

            handled, stored = [], []
            async with SessionLocal() as session:
                for _, events in messages:
                    for msg_id, data in events:
                        handled.append(msg_id)
                        try:
                            incident = json.loads(data["data"])
                            session.add(Incident(**{("meta" if k == "metadata" else k): incident.get(k)
                                                    for k in CONTRACT_FIELDS}))
                            stored.append(incident["event_id"])
                        except (KeyError, json.JSONDecodeError) as e:
                            print(f"[Backend] Skipping message {msg_id}: not in the contract format ({e})", flush=True)
                # acknowledge only after the commit succeeds, so a failed save is redelivered
                await session.commit()
            await r.xack(INCIDENT_STREAM, CONSUMER_GROUP, *handled)
            for event_id in stored:
                print(f"[Backend] Stored incident {event_id}", flush=True)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Backend] Consumer error: {e}", flush=True)
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    task = asyncio.create_task(consume_incidents(r))

    yield

    task.cancel()
    await r.aclose()


app = FastAPI(title="Safety Monitor API", version="1.0.0", lifespan=lifespan)
Path(MEDIA_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/incidents")
async def list_incidents(limit: int = 50, severity: str | None = None, camera_id: str | None = None,
                         event_type: str | None = None):
    async with SessionLocal() as session:
        q = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
        if severity:
            q = q.where(Incident.severity == severity.upper())
        if camera_id:
            q = q.where(Incident.camera_id == camera_id)
        if event_type:
            q = q.where(Incident.event_type == event_type)
        rows = (await session.execute(q)).scalars().all()
        return [_incident_to_dict(r) for r in rows]


@app.get("/incidents/{event_id}")
async def get_incident(event_id: str):
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Incident).where(Incident.event_id == event_id)
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")
        return _incident_to_dict(row)


def _incident_to_dict(row: Incident) -> dict:
    d = {k: getattr(row, "meta" if k == "metadata" else k) for k in CONTRACT_FIELDS}
    d["received_at"] = row.created_at.isoformat(timespec="seconds") + "Z"
    return d


@app.post("/reports", status_code=201)
async def save_report(report: ReportIn):
    async with SessionLocal() as session:
        if not await session.get(Incident, report.event_id):
            raise HTTPException(status_code=404, detail="Incident not found")
        await session.merge(Report(**report.model_dump()))
        await session.commit()
    return {"event_id": report.event_id}


@app.get("/incidents/{event_id}/report")
async def get_report(event_id: str):
    async with SessionLocal() as session:
        row = await session.get(Report, event_id)
        if not row:
            raise HTTPException(status_code=404, detail="No report for this incident yet")
        return _report_to_dict(row)


@app.get("/reports")
async def list_reports(limit: int = 50):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Report).order_by(Report.created_at.desc()).limit(limit))).scalars().all()
        return [_report_to_dict(r) for r in rows]


def _report_to_dict(row: Report) -> dict:
    return {"event_id": row.event_id, "markdown": row.markdown, "generated_by": row.generated_by,
            "delivery": row.delivery, "created_at": row.created_at.isoformat(timespec="seconds") + "Z"}
