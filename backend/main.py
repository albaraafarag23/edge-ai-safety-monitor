import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import String, DateTime, Text, select
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

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp_start: Mapped[str | None] = mapped_column(String)
    timestamp_end: Mapped[str | None] = mapped_column(String)
    camera_id: Mapped[str | None] = mapped_column(String)
    plugin_id: Mapped[str | None] = mapped_column(String)
    rule_id: Mapped[str | None] = mapped_column(String)
    event_type: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str | None] = mapped_column(String)
    zone_id: Mapped[str | None] = mapped_column(String)
    objects_involved: Mapped[str | None] = mapped_column(Text)
    rule_triggered: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


INCIDENT_COLUMNS = {c.name for c in Incident.__table__.columns} - {"created_at"}


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

            async with SessionLocal() as session:
                for _, events in messages:
                    for event_id, data in events:
                        row = Incident(**{k: v for k, v in data.items() if k in INCIDENT_COLUMNS})
                        session.add(row)
                        await r.xack(INCIDENT_STREAM, CONSUMER_GROUP, event_id)
                        print(f"[Backend] Stored incident {data.get('incident_id', '?')}", flush=True)
                await session.commit()

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
async def list_incidents(limit: int = 50, severity: str | None = None):
    async with SessionLocal() as session:
        q = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
        if severity:
            q = q.where(Incident.severity == severity)
        rows = (await session.execute(q)).scalars().all()
        return [_incident_to_dict(r) for r in rows]


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")
        return _incident_to_dict(row)


def _incident_to_dict(row: Incident) -> dict:
    return {c.name: getattr(row, c.name) for c in Incident.__table__.columns}
