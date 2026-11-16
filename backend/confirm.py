"""Confirm it's you before a risky change on this box (switching a rule off, timings, zones, accounts, face photos).

On while the box is linked to the SiteSentry portal (CONFIRM_CHANGES=auto, the default; "on" / "off" to force it).
A change answers 428 "confirm:portal" or "confirm:password" when the person hasn't confirmed in the last CONFIRM_S:
  - people who come from the portal confirm there, with their passkey: the portal sends them back with a one-use
    token (portal_link.portal_sign_in, purpose "confirm");
  - accounts made on the box confirm with their password: POST /auth/confirm.
The console asks for it, then repeats the change by itself. A confirmation belongs to one signed-in browser.
"""
import hashlib
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import auth
from models import User

CONFIRM_S = int(os.getenv("CONFIRM_S", "300"))
_MODE = os.getenv("CONFIRM_CHANGES", "auto").lower()
ON = _MODE == "on" or (_MODE == "auto" and bool(os.getenv("PORTAL_URL")))
router = APIRouter(prefix="/auth", tags=["auth"])
_redis: aioredis.Redis | None = None


def init(redis_url: str):
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)


def _key(request: Request) -> str:
    cookie = request.cookies.get(auth.COOKIE_NAME) or ""
    return "confirmed:" + hashlib.sha256(cookie.encode()).hexdigest()


async def mark(request: Request):
    if _redis is not None:
        await _redis.set(_key(request), "1", ex=CONFIRM_S)


async def required(request: Request, me: User = Depends(auth.current_user)):
    """Add to a risky route: `_: None = Depends(confirm.required)`."""
    if not ON or _redis is None:
        return
    if await _redis.exists(_key(request)):
        return
    raise HTTPException(status_code=428, detail="confirm:portal" if me.source == "portal" else "confirm:password")


class ConfirmIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/confirm", status_code=204)
async def confirm_with_password(body: ConfirmIn, request: Request, me: User = Depends(auth.current_user)):
    if me.source == "portal":
        raise HTTPException(status_code=409, detail="Confirm through the portal")
    keys = [f"email:{me.email}", f"ip:{auth.client_address(request)}"]
    wait = auth.login_limiter.retry_after(keys)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many tries. Try again in {(wait + 59) // 60} min.")
    if not await auth.authenticate(me.email, body.password):
        auth.login_limiter.failed(keys)
        raise HTTPException(status_code=401, detail="Wrong password")
    auth.login_limiter.succeeded(keys)
    await mark(request)


async def close():
    if _redis is not None:
        await _redis.aclose()
