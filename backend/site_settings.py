"""Site settings changed in the console. For now there is one: when the end-of-day summary email goes out.

Stored in Postgres and mirrored to Redis, where ai_reporting/digest.py reads it:
  site:digest_time             "HH:MM" (site time) or "off". No key = nobody chose in the console, so
                               ai_reporting uses its DIGEST_TIME from .env.
Redis isn't persistent, so the backend rewrites the key at startup and every RESYNC_S seconds.
ai_reporting says what it can do in  ai_reporting:email:state  {"configured", "recipients", "default_time",
"timezone"} (expires when it stops), so the console can say whether a summary will really be sent.
"""
import asyncio
import json
import os
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import auth
from models import SessionLocal, SiteSetting, User, iso

SITE_TIMEZONE = os.getenv("SITE_TIMEZONE", "Africa/Cairo")
DIGEST_KEY = "site:digest_time"
EMAIL_STATE_KEY = "ai_reporting:email:state"
RESYNC_S = 30
OFF = "off"

router = APIRouter(prefix="/settings", tags=["settings"])
_redis: aioredis.Redis | None = None


class DailySummaryIn(BaseModel):
    """time = "HH:MM" in site time; null switches the summary off."""
    time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


async def _row(session) -> SiteSetting | None:
    return await session.get(SiteSetting, "digest_time")


async def sync_redis():
    async with SessionLocal() as session:
        row = await _row(session)
    if row is None:
        await _redis.delete(DIGEST_KEY)
    else:
        await _redis.set(DIGEST_KEY, row.value.get("time") or OFF)


async def keep_synced(redis_url: str):
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    while True:
        try:
            await sync_redis()
        except Exception as e:   # Redis or Postgres briefly away: try again
            print(f"[Backend] Site settings not synced to Redis ({e})", flush=True)
        await asyncio.sleep(RESYNC_S)


async def close():
    if _redis:
        await _redis.aclose()


async def _daily_summary() -> dict:
    async with SessionLocal() as session:
        row = await _row(session)
    try:
        state = json.loads(await _redis.get(EMAIL_STATE_KEY) or "null") if _redis else None
    except Exception:
        state = None
    state = state if isinstance(state, dict) else {}
    chosen = row is not None
    return {
        # the time that applies: the console's choice, otherwise the one in .env (null = off)
        "time": (row.value.get("time") if chosen else state.get("default_time")) or None,
        "set_in_console": chosen,
        "timezone": state.get("timezone") or SITE_TIMEZONE,
        # null = the reporting service isn't answering, so it isn't known
        "email_ready": state.get("configured"),
        "recipients": state.get("recipients"),
        "changed_by": row.changed_by if chosen else None,
        "changed_at": iso(row.changed_at) if chosen else None,
    }


@router.get("/daily-summary")
async def get_daily_summary():
    return await _daily_summary()


@router.put("/daily-summary")
async def set_daily_summary(body: DailySummaryIn, me: User = Depends(auth.require_admin)):
    async with SessionLocal() as session:
        row = await _row(session)
        if row is None:
            row = SiteSetting(key="digest_time")
            session.add(row)
        row.value = {"time": body.time}
        row.changed_by, row.changed_at = me.name, datetime.utcnow()
        await session.commit()
    await sync_redis()
    print(f"[Backend] {me.name} set the daily summary to {body.time or 'off'}", flush=True)
    return await _daily_summary()
