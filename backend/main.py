import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

import analytics
import auth
import cameras
import users
from live import broadcaster
from models import STATUSES, Base, Incident, Report, SessionLocal, User, engine

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
INCIDENT_STREAM = "incidents"
CONSUMER_GROUP = "backend"
CONSUMER_NAME = "backend_01"
# snapshots and clips written by cv_pipeline, served at /media/...
MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")


class ReportIn(BaseModel):
    event_id: str
    markdown: str
    generated_by: str
    delivery: dict = {}


class LoginIn(BaseModel):
    email: str
    password: str


class StatusIn(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]
    note: str | None = None


async def consume_incidents(r: aioredis.Redis):
    try:
        await r.xgroup_create(INCIDENT_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            print(f"[Backend] xgroup_create: {e}", flush=True)

    print("[Backend] Consuming incidents stream...", flush=True)

    while True:
        try:
            messages = await r.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {INCIDENT_STREAM: ">"},
                                          count=10, block=1000)
            if not messages:
                continue

            handled, stored = [], []
            async with SessionLocal() as session:
                for _, events in messages:
                    for msg_id, data in events:
                        handled.append(msg_id)
                        try:
                            row = Incident.from_contract(json.loads(data["data"]))
                            session.add(row)
                            stored.append(row)
                        except (KeyError, json.JSONDecodeError) as e:
                            print(f"[Backend] Skipping message {msg_id}: not in the contract format ({e})", flush=True)
                # acknowledge only after the commit succeeds, so a failed save is redelivered
                await session.commit()
            await r.xack(INCIDENT_STREAM, CONSUMER_GROUP, *handled)
            for row in stored:
                print(f"[Backend] Stored incident {row.event_id}", flush=True)
                broadcaster.publish("incident", row.to_dict())

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Backend] Consumer error: {e}", flush=True)
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await auth.ensure_admin()

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    cameras.init(REDIS_URL)
    task = asyncio.create_task(consume_incidents(r))

    yield

    task.cancel()
    await r.aclose()
    await cameras.close()


app = FastAPI(title="Safety Monitor API", version="1.2.0", lifespan=lifespan)

# The dashboard is served from the same origin (nginx / Vite proxy /api), so CORS only matters
# for other tools; credentials (the session cookie) are never sent cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)
MEDIA_ROOT = Path(MEDIA_DIR).resolve()
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# everything on this router needs a signed-in user (session cookie, see auth.py)
protected = APIRouter(dependencies=[Depends(auth.current_user)])


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- sign-in ----------

@app.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    keys = [f"email:{body.email.strip().lower()}", f"ip:{auth.client_address(request)}"]
    wait = auth.login_limiter.retry_after(keys)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {(wait + 59) // 60} min.",
                            headers={"Retry-After": str(wait)})
    user = await auth.authenticate(body.email, body.password)
    if not user:
        auth.login_limiter.failed(keys)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    auth.login_limiter.succeeded(keys)
    auth.set_session_cookie(response, user)
    return user.to_dict()


@app.post("/auth/logout", status_code=204)
async def logout(response: Response):
    auth.clear_session_cookie(response)


@app.get("/auth/me")
async def me(user: User = Depends(auth.current_user)):
    return user.to_dict()


# ---------- media (snapshots and clips) ----------

@protected.get("/media/{path:path}")
async def media(path: str):
    file = (MEDIA_ROOT / path).resolve()
    # stay inside the media folder, and skip files still being written (".part-...")
    if not file.is_relative_to(MEDIA_ROOT) or file.name.startswith(".") or not file.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file)  # supports Range requests, so clips can be seeked


# ---------- incidents ----------

@protected.get("/incidents")
async def list_incidents(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: str | None = None,
    camera_id: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    hours: float | None = Query(None, gt=0, description="only incidents received in the last N hours"),
):
    filters = []
    if severity:
        filters.append(Incident.severity == severity.upper())
    if camera_id:
        filters.append(Incident.camera_id == camera_id)
    if event_type:
        filters.append(Incident.event_type == event_type)
    if status:
        filters.append(Incident.status == status)
    if hours:
        filters.append(Incident.created_at >= datetime.utcnow() - timedelta(hours=hours))

    async with SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(Incident).where(*filters))
        rows = (await session.execute(
            select(Incident, Report)
            .outerjoin(Report, Report.event_id == Incident.event_id)
            .where(*filters)
            .order_by(Incident.created_at.desc())
            .limit(limit).offset(offset)
        )).all()
    response.headers["X-Total-Count"] = str(total)
    return [incident.to_dict(report) for incident, report in rows]


@protected.get("/incidents/{event_id}")
async def get_incident(event_id: str):
    async with SessionLocal() as session:
        incident = await session.get(Incident, event_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return incident.to_dict(await session.get(Report, event_id))


@protected.patch("/incidents/{event_id}/status", dependencies=[Depends(auth.can_handle_incidents)])
async def set_status(event_id: str, body: StatusIn):
    async with SessionLocal() as session:
        incident = await session.get(Incident, event_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        incident.status = body.status
        incident.status_note = body.note
        incident.status_updated_at = datetime.utcnow()
        await session.commit()
        result = incident.to_dict(await session.get(Report, event_id))
    broadcaster.publish("status", {"event_id": event_id, "status": body.status})
    return result


# ---------- reports ----------

@app.post("/reports", status_code=201, dependencies=[Depends(auth.internal_service)])
async def save_report(report: ReportIn):
    async with SessionLocal() as session:
        if not await session.get(Incident, report.event_id):
            raise HTTPException(status_code=404, detail="Incident not found")
        await session.merge(Report(**report.model_dump()))
        await session.commit()
    broadcaster.publish("report", {"event_id": report.event_id, "generated_by": report.generated_by,
                                   "delivery_status": report.delivery.get("status")})
    return {"event_id": report.event_id}


@protected.get("/incidents/{event_id}/report")
async def get_report(event_id: str):
    async with SessionLocal() as session:
        row = await session.get(Report, event_id)
        if not row:
            raise HTTPException(status_code=404, detail="No report for this incident yet")
        return row.to_dict()


@protected.get("/reports")
async def list_reports(limit: int = Query(50, ge=1, le=200)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Report).order_by(Report.created_at.desc()).limit(limit))).scalars().all()
        return [r.to_dict() for r in rows]


# ---------- dashboard ----------

@protected.get("/stats")
async def stats(hours: float = Query(24, gt=0, le=24 * 90)):
    """Counts for the overview page, over the last `hours`."""
    since = datetime.utcnow() - timedelta(hours=hours)
    recent = Incident.created_at >= since

    async def counts(column):
        rows = (await session.execute(select(column, func.count()).where(recent).group_by(column))).all()
        return {k: v for k, v in rows}

    async with SessionLocal() as session:
        by_severity = await counts(Incident.severity)
        by_event_type = await counts(Incident.event_type)
        by_status = await counts(Incident.status)
        by_camera = await counts(Incident.camera_id)
        bucket = func.date_trunc("hour", Incident.created_at)
        timeline = (await session.execute(
            select(bucket, func.count()).where(recent).group_by(bucket).order_by(bucket))).all()

    return {
        "hours": hours,
        "total": sum(by_severity.values()),
        "open": by_status.get("open", 0),
        "by_severity": by_severity,
        "by_event_type": by_event_type,
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "by_camera": by_camera,
        "timeline": [{"hour": t.isoformat() + "Z", "count": c} for t, c in timeline],
    }


@protected.get("/filters")
async def filter_options():
    """Values that exist in the data, for the dashboard's filter dropdowns."""
    async with SessionLocal() as session:
        cameras = (await session.execute(select(Incident.camera_id).distinct().order_by(Incident.camera_id))).scalars().all()
        types = (await session.execute(select(Incident.event_type).distinct().order_by(Incident.event_type))).scalars().all()
    return {"camera_ids": cameras, "event_types": types, "severities": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            "statuses": list(STATUSES)}


@protected.get("/events")
async def events(request: Request):
    """Server-Sent Events: `incident`, `report` and `status` events as they happen."""
    return StreamingResponse(broadcaster.stream(request.is_disconnected), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


protected.include_router(cameras.router)
protected.include_router(analytics.router)
protected.include_router(users.router)
app.include_router(users.account)
app.include_router(protected)
