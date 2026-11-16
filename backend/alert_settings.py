"""Who gets alert emails, chosen by each person on their Account page: their address (the sign-in email unless
they give another), from which severity up, and whether they want the end-of-day summary.

Defaults when someone hasn't chosen: managers and supervisors get High and Critical; viewers get nothing; managers
get the summary. The shared demo account never gets email.

The list is mirrored to Redis for ai_reporting (notify.py):
  notify:recipients   [{"email", "level": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW", "summary": bool}, ...]
written at startup, on every change and every RESYNC_S seconds (Redis isn't persistent). People with alerts off
and no summary are left out. SUPERVISOR_EMAILS in .env still works as a fixed extra list.
"""
import asyncio
import json
import re
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

import auth
from models import SessionLocal, User

KEY = "notify:recipients"
RESYNC_S = 30
LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "OFF")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")

router = APIRouter(prefix="/auth/alerts", tags=["account"])
_redis: aioredis.Redis | None = None


def default_level(role: str) -> str:
    return "OFF" if role == "viewer" else "HIGH"


def effective(user: User) -> dict:
    demo = user.to_dict()["demo"]
    return {
        "email": user.alert_email or user.email,
        "own_email": user.alert_email is not None,
        "level": "OFF" if demo else (user.alert_level or default_level(user.role)),
        "summary": False if demo else (user.daily_summary if user.daily_summary is not None else user.role == "manager"),
        "chosen": user.alert_level is not None,
        "locked": demo,
    }


class AlertsIn(BaseModel):
    email: str | None = Field(None, max_length=254)   # None or "" = use the sign-in email
    level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "OFF"]
    summary: bool

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = (value or "").strip()
        if value and not EMAIL.match(value):
            raise ValueError("That doesn't look like an email address")
        return value or None


@router.get("")
async def my_alerts(me: User = Depends(auth.current_user)):
    return effective(me)


@router.put("")
async def set_my_alerts(body: AlertsIn, me: User = Depends(auth.current_user)):
    if me.to_dict()["demo"]:
        raise HTTPException(status_code=403, detail="The demo account doesn't get email")
    async with SessionLocal() as session:
        user = await session.get(User, me.id)
        user.alert_email = body.email.lower() if body.email else None
        user.alert_level, user.daily_summary = body.level, body.summary
        await session.commit()
        result = effective(user)
    auth.forget_users()
    await sync_redis()
    return result


async def recipients() -> list[dict]:
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).where(User.active.is_(True)))).all()
    out, seen = [], set()
    for user in users:
        e = effective(user)
        if (e["level"] == "OFF" and not e["summary"]) or e["email"] in seen:
            continue
        seen.add(e["email"])
        out.append({"email": e["email"], "level": e["level"], "summary": e["summary"]})
    return out


async def sync_redis():
    if _redis:
        await _redis.set(KEY, json.dumps(await recipients()))


async def keep_synced(redis_url: str):
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    while True:
        try:
            await sync_redis()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Backend] Couldn't sync alert recipients to Redis: {e}", flush=True)
        await asyncio.sleep(RESYNC_S)


async def close():
    if _redis:
        await _redis.aclose()
