"""This box and the SiteSentry portal (docs/portal.md, "Boxes"). Off unless PORTAL_URL is set.

Every CHECKIN_S: register (first time), then check in with health only (cameras, frames per second, the rule set
running, disk). The portal answers with this site's people and a licence; both are signed checks:
  - requests: signed with this box's own Ed25519 key (made here on the first start, kept in the database);
  - answers: the portal's key is pinned on the first registration; a later answer signed by another key is ignored.
People from the portal become accounts here (source "portal"); dropped ones are switched off. Accounts made on
the box itself are never touched. The licence goes to Redis for the drive loader (LICENCE_REQUIRED).

One-click sign-in: GET /auth/portal?token=... (from the portal's "Open console"): a portal-signed token for this
box, 60 s, one use.
"""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import time
from datetime import datetime
from urllib.parse import urlencode

import httpx
import redis.asyncio as aioredis
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

import alert_settings
import auth
import box_events
import confirm
from models import BoxLink, SessionLocal, User

PORTAL_URL = os.getenv("PORTAL_URL", "").rstrip("/")
# the address people's browsers use, when the box reaches the portal another way (on the Jetson: an internal name)
PORTAL_PUBLIC_URL = (os.getenv("PORTAL_PUBLIC_URL") or PORTAL_URL).rstrip("/")
BOX_SERIAL = os.getenv("BOX_SERIAL") or socket.gethostname()
CONSOLE_URL = os.getenv("CONSOLE_URL", "").rstrip("/")
MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
VERSION = os.getenv("BOX_VERSION", "")
CHECKIN_S = float(os.getenv("PORTAL_CHECKIN_S", "60"))
LICENCE_KEY = "site:licence"    # read by plugin_loader
STATUS_KEY = "portal:link"      # what the console shows about the link

router = APIRouter(tags=["portal"])
_redis: aioredis.Redis | None = None


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


async def link() -> BoxLink:
    async with SessionLocal() as session:
        row = await session.get(BoxLink, 1)
        if not row:
            pem = Ed25519PrivateKey.generate().private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            row = BoxLink(id=1, private_pem=pem.decode())
            session.add(row)
            await session.commit()
        return row


def box_key(row: BoxLink) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(row.private_pem.encode(), password=None)


def public_key(row: BoxLink) -> str:
    return b64(box_key(row).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def read_signed(token: str, portal_key: str | None) -> dict | None:
    """A portal-signed "<body>.<signature>" -> its payload, or None if it isn't signed by the pinned key."""
    if not token or not portal_key or token.count(".") != 1:
        return None
    body, signature = token.split(".")
    try:
        Ed25519PublicKey.from_public_bytes(unb64(portal_key)).verify(unb64(signature), body.encode())
        payload = json.loads(unb64(body))
    except (ValueError, InvalidSignature):
        return None
    return payload if isinstance(payload, dict) else None


async def call(client: httpx.AsyncClient, row: BoxLink, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    ts = str(int(time.time() * 1000))
    message = f"POST {path}\n{ts}\n{hashlib.sha256(body).hexdigest()}".encode()
    response = await client.post(PORTAL_URL + path, content=body, headers={
        "Content-Type": "application/json", "X-Box-Serial": BOX_SERIAL, "X-Box-Time": ts,
        "X-Box-Signature": b64(box_key(row).sign(message))})
    if response.status_code >= 400:
        raise RuntimeError(f"{path}: {response.status_code} {response.text[:200]}")
    return response.json()


async def health() -> dict:
    """What the overseer may see: is it working. Never pictures, incidents or names."""
    cameras, running = [], None
    async for key in _redis.scan_iter("camera:*:info"):
        info = await _redis.hgetall(key)
        running = running or info.get("plugin_id")
        cameras.append({"id": key.split(":")[1], "fps": float(info.get("fps") or 0),
                        "updated_at": info.get("updated_at")})
    try:
        plugin = json.loads(await _redis.get("site:plugin") or "{}")
    except ValueError:
        plugin = {}
    try:
        disk = shutil.disk_usage(MEDIA_DIR)
        disk_used = round(100 * disk.used / disk.total)
    except OSError:
        disk_used = None
    # drive mode: the loader says what runs; fixed mode: the detector does (camera info)
    return {"cameras": sorted(cameras, key=lambda c: c["id"]), "rules": plugin.get("plugin_id") or running,
            "rules_state": plugin.get("state"), "disk_used_pct": disk_used}


async def sync_people(people: list[dict]):
    wanted = {p["email"].lower(): p for p in people if isinstance(p, dict) and p.get("email")}
    changed = False
    async with SessionLocal() as session:
        users = (await session.scalars(select(User))).all()
        by_email = {u.email: u for u in users}
        for email, p in wanted.items():
            role = p.get("role") if p.get("role") in auth.ROLES else "viewer"
            user = by_email.get(email)
            if user and user.to_dict()["demo"]:
                continue
            if not user:
                # no usable password: portal accounts sign in through the portal
                session.add(User(email=email, name=p.get("name") or email, role=role, source="portal",
                                 password_hash=auth.hash_password(secrets.token_urlsafe(32))))
                changed = True
            elif (user.name, user.role, user.active, user.source) != (p.get("name") or user.name, role, True, "portal"):
                user.name, user.role, user.active, user.source = p.get("name") or user.name, role, True, "portal"
                changed = True
        for user in users:
            if user.source == "portal" and user.email not in wanted and user.active:
                user.active = False
                changed = True
        await session.commit()
    if changed:
        auth.forget_users()
        await alert_settings.sync_redis()
        print(f"[Portal] People in step with the portal: {len(wanted)}", flush=True)


async def once(client: httpx.AsyncClient):
    row = await link()
    if not row.portal_key or row.status is None:
        answer = await call(client, row, "/api/box/register", {
            "serial": BOX_SERIAL, "public_key": public_key(row), "console_url": CONSOLE_URL or None,
            "version": VERSION or None})
        async with SessionLocal() as session:
            r = await session.get(BoxLink, 1)
            r.portal_key = r.portal_key or answer.get("portal_key")
            r.status = answer.get("status")
            await session.commit()
        row = await link()
    events = await box_events.take()
    answer = await call(client, row, "/api/box/checkin", {"console_url": CONSOLE_URL or None,
                                                          "version": VERSION or None, "health": await health(),
                                                          "events": events})
    await box_events.taken(len(events))   # the portal has them (an error above keeps them for the next try)
    if answer.get("portal_key") != row.portal_key:
        raise RuntimeError("the portal answered with a different key than the one this box trusts: ignored")
    licence = read_signed(answer.get("licence") or "", row.portal_key)
    if answer.get("licence") and (not licence or licence.get("serial") != BOX_SERIAL):
        raise RuntimeError("the licence isn't signed by the portal this box trusts, or isn't for this box: ignored")
    async with SessionLocal() as session:
        r = await session.get(BoxLink, 1)
        r.status, r.site, r.company = answer.get("status"), answer.get("site"), answer.get("company")
        r.last_contact = datetime.utcnow()
        if licence:
            r.licence = answer["licence"]
        await session.commit()
    if answer.get("status") == "approved":
        await sync_people(answer.get("people") or [])


async def publish(row: BoxLink, error: str | None = None):
    """The licence for the drive loader, and the link's state for the console."""
    licence = read_signed(row.licence or "", row.portal_key)
    if licence:
        await _redis.set(LICENCE_KEY, json.dumps({"serial": licence.get("serial"), "plugins": licence.get("plugins"),
                                                   "cancelled_drives": licence.get("cancelled_drives") or [],
                                                   "valid_until": licence.get("valid_until")}))
    await _redis.set(STATUS_KEY, json.dumps({
        "portal": PORTAL_URL, "serial": BOX_SERIAL, "status": row.status, "site": row.site, "company": row.company,
        "last_contact": row.last_contact.isoformat() + "Z" if row.last_contact else None,
        "licence_until": licence.get("valid_until") if licence else None, "error": error}))


async def keep_linked(redis_url: str):
    global _redis
    if not PORTAL_URL:
        return
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    print(f"[Portal] Linking this box ({BOX_SERIAL}) to {PORTAL_URL}", flush=True)
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            error = None
            try:
                await once(client)
            except asyncio.CancelledError:
                raise
            except Exception as e:   # noqa: BLE001: no internet, portal asleep, ...: try again next round
                error = f"{type(e).__name__}: {e}"[:300]
                print(f"[Portal] {error}", flush=True)
            try:
                await publish(await link(), error)
            except Exception as e:   # noqa: BLE001
                print(f"[Portal] Couldn't publish the link state: {e}", flush=True)
            await asyncio.sleep(CHECKIN_S)


# ---------- one-click sign-in from the portal ----------

@router.get("/auth/options")
async def sign_in_options():
    """What the sign-in page can offer besides a password."""
    return {"portal_url": PORTAL_PUBLIC_URL or None}


@router.get("/auth/confirm-url")
async def confirm_url(back: str = "/app", me: User = Depends(auth.current_user)):
    """Where a portal account confirms a risky change: the portal asks for the passkey, then sends them back."""
    if not PORTAL_URL or me.source != "portal":
        raise HTTPException(status_code=409, detail="Confirm with your password")
    return {"url": f"{PORTAL_PUBLIC_URL}/confirm?{urlencode({'box': BOX_SERIAL, 'back': _safe_back(back)})}"}


def _safe_back(path: str) -> str:
    """Only a page of this console (no other site, no tricks like //evil.example)."""
    return path if path.startswith("/app") and not path.startswith("//") and "\\" not in path else "/app"


@router.get("/auth/portal")
async def portal_sign_in(request: Request, token: str = ""):
    row = await link() if PORTAL_URL else None
    payload = read_signed(token, row.portal_key if row else None)
    failed = RedirectResponse("/login?portal=failed", status_code=303)
    if not payload or payload.get("aud") != BOX_SERIAL or float(payload.get("exp") or 0) < time.time():
        return failed
    if _redis is None or not await _redis.set(f"portal:jti:{payload.get('jti')}", "1", nx=True, ex=300):
        return failed   # each token works once
    if payload.get("purpose") == "confirm":
        # back from confirming a change with the passkey: same person, same browser, already signed in here
        me = await auth.user_from_token(request.cookies.get(auth.COOKIE_NAME))
        if not me or me.email != str(payload.get("sub", "")).lower():
            return failed
        await confirm.mark(request)
        back = _safe_back(str(payload.get("back") or "/app"))
        return RedirectResponse(back + ("&" if "?" in back else "?") + "confirmed=1", status_code=303)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == str(payload.get("sub", "")).lower()))
        if not user or not user.active or user.source != "portal":
            return failed
        user.last_login_at = datetime.utcnow()
        await session.commit()
    response = RedirectResponse("/app", status_code=303)
    auth.set_session_cookie(response, user)
    return response
