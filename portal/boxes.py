"""Boxes (Jetsons on site) and the portal: Lock 2 and the one-click sign-in.

A box makes its own Ed25519 key on first start and signs every request with it:
  X-Box-Serial, X-Box-Time (unix ms), X-Box-Signature = sign("<METHOD> <path>\\n<time>\\n<sha256 hex of body>")
  POST /api/box/register   {serial, public_key, console_url, version}   -> waits for the overseer ("waiting")
  POST /api/box/checkin    {console_url, version, health}               -> every minute
The check-in answer carries, once the overseer has assigned the box to a site: the site's people (accounts the
box keeps in step), and a licence signed by the portal (which rule sets it may run, valid 7 days). Nothing from
the cameras is ever sent here: health only.

One-click sign-in: a manager, supervisor or viewer asks for their site's console; the portal signs a token
(60 s, one use, for that box only) and the box signs them in. The overseer can't: they never see footage.
"""
import asyncio
import base64
import hashlib
import json
import secrets
import time
from datetime import timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

import audit
import mailer
import security as sec
from models import Box, Company, PortalKey, Site, User, UserSite, SessionLocal, now
from security import Signed, aware, fresh, signed_in

LICENCE_DAYS = 7
CLOCK_SKEW_S = 300
SILENT_MIN = 10
TOKEN_S = 60

box_api = APIRouter(prefix="/api/box", tags=["box"])          # called by boxes: no browser, no cookies
router = APIRouter(prefix="/api", tags=["boxes"])             # called by the screens

_key: Ed25519PrivateKey | None = None


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


async def portal_key() -> Ed25519PrivateKey:
    global _key
    if _key is None:
        async with SessionLocal() as session:
            row = await session.scalar(select(PortalKey).order_by(PortalKey.id).limit(1))
            if not row:
                pem = Ed25519PrivateKey.generate().private_bytes(
                    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
                row = PortalKey(private_pem=pem.decode())
                session.add(row)
                await session.commit()
        _key = serialization.load_pem_private_key(row.private_pem.encode(), password=None)
    return _key


async def portal_public() -> str:
    raw = (await portal_key()).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return b64(raw)


async def sign(payload: dict) -> str:
    """payload -> "<base64 json>.<base64 signature>" (what boxes check with the pinned portal key)."""
    body = b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return body + "." + b64((await portal_key()).sign(body.encode()))


# ---------- requests from boxes ----------

def signed_message(method: str, path: str, ts: str, body: bytes) -> bytes:
    return f"{method} {path}\n{ts}\n{hashlib.sha256(body).hexdigest()}".encode()


def check_box_signature(request: Request, body: bytes, public_key: str) -> int:
    """The request's time (ms) if the signature and time are good; raises otherwise."""
    ts = request.headers.get("x-box-time", "")
    try:
        when = int(ts)
        Ed25519PublicKey.from_public_bytes(unb64(public_key)).verify(
            unb64(request.headers.get("x-box-signature", "")),
            signed_message(request.method, request.url.path, ts, body))
    except (ValueError, InvalidSignature):
        raise HTTPException(status_code=401, detail="Bad box signature")
    if abs(when / 1000 - time.time()) > CLOCK_SKEW_S:
        raise HTTPException(status_code=401, detail="Box clock is off by more than 5 minutes")
    return when


class Hello(BaseModel):
    serial: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    public_key: str = Field(max_length=64)
    console_url: str | None = Field(None, max_length=300)
    version: str | None = Field(None, max_length=60)


@box_api.post("/register")
async def register(request: Request):
    sec.limit(request, "box-register", 30)
    body = await request.body()
    try:
        hello = Hello.model_validate_json(body)
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad registration")
    if request.headers.get("x-box-serial") != hello.serial:
        raise HTTPException(status_code=401, detail="Bad box signature")
    check_box_signature(request, body, hello.public_key)   # proves it holds the key it is registering
    async with SessionLocal() as session:
        box = await session.scalar(select(Box).where(Box.serial == hello.serial))
        if box and box.public_key != hello.public_key:
            new = None
        elif not box:
            box = new = Box(serial=hello.serial, public_key=hello.public_key, status="waiting",
                            console_url=hello.console_url, health={"version": hello.version})
            session.add(box)
            await session.commit()
        else:
            new = False
    if new is None:
        await audit.record("system", "box_key_mismatch", f"Something calling itself box {hello.serial} tried to "
                           "register with a different key. It may be a copied or replaced box: refused.",
                           serial=hello.serial, address=sec.client_address(request))
        await mail_overseers(f"SiteSentry: box {hello.serial} refused",
                             f"A device claiming to be box {hello.serial} tried to register with a different key "
                             f"from {sec.client_address(request)}. It was refused. If the box was replaced, block "
                             "the old one in the portal and register the new one under a new serial.")
        raise HTTPException(status_code=409, detail="This serial is registered with another key")
    if new:
        await audit.record("system", "box_waiting", f"A new box, {hello.serial}, asked to join.",
                           serial=hello.serial, address=sec.client_address(request))
        await mail_overseers(f"SiteSentry: new box {hello.serial} wants to join",
                             f"Box {hello.serial} contacted the portal. Until you assign it to a site it runs no "
                             f"licensed rules.\n\n{sec.PORTAL_URL}/boxes")
    return {"status": box.status, "portal_key": await portal_public()}


class BoxEvent(BaseModel):
    at: str | None = Field(None, max_length=40)
    kind: str = Field(max_length=40, pattern=r"^[a-z_]+$")
    actor: str | None = Field(None, max_length=120)
    summary: str = Field(max_length=300)
    details: dict = {}


class Checkin(BaseModel):
    console_url: str | None = Field(None, max_length=300)
    version: str | None = Field(None, max_length=60)
    health: dict = {}
    events: list[dict] = Field(default_factory=list, max_length=100)   # BoxEvent each; a bad one is skipped


ALERT_KINDS = {"signin_failed", "drive_refused"}   # emailed to the overseer (the rest only go in the log)


async def site_people(site: Site) -> list[dict]:
    """Who the box should have accounts for: the company's managers (all sites, or this one) and the
    supervisors and viewers linked to this site."""
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).where(User.company_id == site.company_id,
                                                          User.active.is_(True)))).all()
        links = (await session.scalars(select(UserSite).where(UserSite.user_id.in_([u.id for u in users])))).all()
    sites_of: dict[int, set[int]] = {}
    for link in links:
        sites_of.setdefault(link.user_id, set()).add(link.site_id)
    out = []
    for u in users:
        mine = sites_of.get(u.id, set())
        if site.id in mine or (u.role == "manager" and not mine):
            out.append({"email": u.email, "name": u.name, "role": u.role})
    return out


@box_api.post("/checkin")
async def checkin(request: Request):
    body = await request.body()
    serial = request.headers.get("x-box-serial", "")
    async with SessionLocal() as session:
        box = await session.scalar(select(Box).where(Box.serial == serial))
    if not box or not box.public_key:
        raise HTTPException(status_code=404, detail="Unknown box: register first")
    when = check_box_signature(request, body, box.public_key)
    try:
        report = Checkin.model_validate_json(body)
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad check-in")
    back = False
    async with SessionLocal() as session:
        box = await session.get(Box, box.id)
        if box.last_seq and when <= box.last_seq:
            raise HTTPException(status_code=409, detail="Replayed check-in")
        back = bool(box.silent_noted)
        box.last_seq, box.last_checkin, box.silent_noted = when, now(), False
        box.health = {**(report.health or {}), "version": report.version}
        if report.console_url:
            box.console_url = report.console_url
        site = await session.get(Site, box.site_id) if box.site_id else None
        company = await session.get(Company, site.company_id) if site else None
        await session.commit()
    if back:
        await audit.record("system", "box_back", f"Box {box.serial} is checking in again.",
                           company.id if company else None, serial=box.serial)
    where = f"{company.name}, {site.name}" if site and company else f"box {box.serial}"
    alerts = []
    for raw in report.events:   # what happened on the box since the last check-in, into the chained log
        try:
            e = BoxEvent.model_validate(raw)
        except ValueError:   # never let one odd event block the check-ins (the box would retry it forever)
            continue
        await audit.record(f"{e.actor or 'box'} (on {box.serial})", f"box_{e.kind}", f"{where}: {e.summary}",
                           company.id if company else None, serial=box.serial, at=e.at, **{"details": e.details})
        if e.kind in ALERT_KINDS:
            alerts.append(f"- {e.at or ''} {e.summary}")
    if alerts:
        await mail_overseers(f"SiteSentry: {len(alerts)} warning(s) from {where}",
                             f"The box at {where} ({box.serial}) reported:\n\n" + "\n".join(alerts)
                             + f"\n\nThe full record is in the portal's security log: {sec.PORTAL_URL}/log")
    answer = {"status": box.status, "portal_key": await portal_public(), "site": None, "company": None,
              "people": [], "licence": None}
    if box.status == "approved" and site and company and company.active:
        answer.update(site=site.name, company=company.name, people=await site_people(site),
                      licence=await sign({"serial": box.serial, "plugins": box.plugins or [],
                                          "issued": int(time.time()),
                                          "valid_until": int(time.time()) + LICENCE_DAYS * 86400}))
    return answer


# ---------- the overseer's side ----------

# Rule sets a licence can name (plugin_id: name). New plugins are added here when they are sold.
RULE_SETS = {"construction_safety": "Construction site safety", "construction_demo": "Construction (demo)",
             "hospital_safety": "Hospital infection control"}


@router.get("/rule-sets")
async def rule_sets(me: Signed = Depends(signed_in)):
    return [{"id": k, "name": v} for k, v in RULE_SETS.items()]


@router.get("/sites")
async def all_sites(me: Signed = Depends(signed_in)):
    """Every site with its company (the overseer, to assign boxes)."""
    if me.user.role != "overseer":
        raise HTTPException(status_code=403, detail="You can't do that")
    async with SessionLocal() as session:
        rows = (await session.execute(select(Site, Company).join(Company, Company.id == Site.company_id)
                                      .order_by(Company.name, Site.name))).all()
    return [{"id": s.id, "name": s.name, "company_id": c.id, "company": c.name} for s, c in rows]


class AssignIn(BaseModel):
    site_id: int
    plugins: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("plugins")
    @classmethod
    def known(cls, v):
        unknown = set(v) - set(RULE_SETS)
        if unknown:
            raise ValueError(f"Unknown rule sets: {sorted(unknown)}")
        return v


@router.post("/boxes/{box_id}/assign")
async def assign(box_id: int, body: AssignIn, me: Signed = Depends(fresh)):
    if me.user.role != "overseer":
        raise HTTPException(status_code=403, detail="You can't do that")
    async with SessionLocal() as session:
        box, site = await session.get(Box, box_id), await session.get(Site, body.site_id)
        if not box or not site:
            raise HTTPException(status_code=404, detail="No such box or site")
        other = await session.scalar(select(Box).where(Box.site_id == site.id, Box.id != box.id,
                                                       Box.status == "approved"))
        if other:
            raise HTTPException(status_code=409, detail=f"{site.name} already has box {other.serial}")
        box.site_id, box.status, box.plugins = site.id, "approved", sorted(set(body.plugins))
        company = await session.get(Company, site.company_id)
        await session.commit()
    await audit.record(me.user, "box_assigned", f"{me.user.name} assigned box {box.serial} to {company.name}, "
                       f"{site.name} (rule sets: {', '.join(box.plugins) or 'none'}).", company.id, serial=box.serial)
    return {"id": box.id, "status": box.status, "site_id": box.site_id, "plugins": box.plugins}


class BoxPatch(BaseModel):
    status: str | None = Field(None, pattern="^(approved|blocked)$")
    plugins: list[str] | None = Field(None, max_length=20)

    @field_validator("plugins")
    @classmethod
    def known(cls, v):
        unknown = set(v or []) - set(RULE_SETS)
        if unknown:
            raise ValueError(f"Unknown rule sets: {sorted(unknown)}")
        return v


@router.patch("/boxes/{box_id}")
async def change_box(box_id: int, body: BoxPatch, me: Signed = Depends(fresh)):
    if me.user.role != "overseer":
        raise HTTPException(status_code=403, detail="You can't do that")
    async with SessionLocal() as session:
        box = await session.get(Box, box_id)
        if not box:
            raise HTTPException(status_code=404, detail="No such box")
        if body.status == "approved" and not box.site_id:
            raise HTTPException(status_code=409, detail="Assign the box to a site first")
        if body.status:
            box.status = body.status
        if body.plugins is not None:
            box.plugins = sorted(set(body.plugins))
        site = await session.get(Site, box.site_id) if box.site_id else None
        await session.commit()
    what = {"blocked": "blocked", "approved": "unblocked"}.get(body.status or "", "changed the licence of")
    await audit.record(me.user, "box_changed", f"{me.user.name} {what} box {box.serial}"
                       + (f" (rule sets: {', '.join(box.plugins or []) or 'none'})" if body.plugins is not None else "")
                       + ".", site.company_id if site else None, serial=box.serial)
    return {"id": box.id, "status": box.status, "plugins": box.plugins}


# ---------- one-click sign-in to a site's console ----------

@router.post("/sites/{site_id}/console")
async def open_console(site_id: int, me: Signed = Depends(signed_in)):
    if me.user.role == "overseer":
        raise HTTPException(status_code=403, detail="The overseer doesn't open site consoles: footage stays with the client")
    async with SessionLocal() as session:
        site = await session.get(Site, site_id)
        box = await session.scalar(select(Box).where(Box.site_id == site_id, Box.status == "approved"))
    if not site or site.company_id != me.user.company_id:
        raise HTTPException(status_code=404, detail="No such site")
    if me.user.email not in {p["email"] for p in await site_people(site)}:
        raise HTTPException(status_code=403, detail="You don't work on this site")
    if not box or not box.console_url:
        raise HTTPException(status_code=409, detail="This site's box hasn't connected yet")
    token = await sign({"aud": box.serial, "sub": me.user.email, "name": me.user.name, "role": me.user.role,
                        "exp": int(time.time()) + TOKEN_S, "jti": secrets.token_urlsafe(12)})
    await audit.record(me.user, "console_opened", f"{me.user.name} opened the console of {site.name}.",
                       site.company_id, serial=box.serial)
    return {"url": f"{box.console_url.rstrip('/')}/api/auth/portal?token={token}"}


class ConfirmIn(BaseModel):
    back: str = Field("/app", max_length=300)


@router.post("/boxes/by-serial/{serial}/confirm")
async def confirm_on_box(serial: str, body: ConfirmIn, me: Signed = Depends(fresh)):
    """A risky change on a site's console, confirmed here with the passkey (the `fresh` check asks for it): a
    one-use token that tells that box this person has just confirmed (backend/confirm.py)."""
    async with SessionLocal() as session:
        box = await session.scalar(select(Box).where(Box.serial == serial, Box.status == "approved"))
        site = await session.get(Site, box.site_id) if box and box.site_id else None
    if not box or not site or not box.console_url or site.company_id != me.user.company_id:
        raise HTTPException(status_code=404, detail="No such box")
    if me.user.email not in {p["email"] for p in await site_people(site)}:
        raise HTTPException(status_code=403, detail="You don't work on this site")
    back = body.back if body.back.startswith("/app") and not body.back.startswith("//") else "/app"
    token = await sign({"aud": box.serial, "sub": me.user.email, "purpose": "confirm", "back": back,
                        "exp": int(time.time()) + TOKEN_S, "jti": secrets.token_urlsafe(12)})
    await audit.record(me.user, "change_confirmed", f"{me.user.name} confirmed a change on the console of "
                       f"{site.name} with their passkey.", site.company_id, serial=box.serial)
    return {"url": f"{box.console_url.rstrip('/')}/api/auth/portal?token={token}"}


# ---------- silent boxes ----------

async def mail_overseers(subject: str, text: str):
    async with SessionLocal() as session:
        emails = (await session.scalars(select(User.email).where(User.role == "overseer",
                                                                 User.active.is_(True)))).all()
    await mailer.send(list(emails), subject, text)


async def note_silent_boxes():
    cutoff = now() - timedelta(minutes=SILENT_MIN)
    async with SessionLocal() as session:
        boxes = (await session.scalars(select(Box).where(Box.status == "approved"))).all()
        silent = [b for b in boxes if not b.silent_noted and (not b.last_checkin or aware(b.last_checkin) < cutoff)]
        for b in silent:
            b.silent_noted = True
        rows = []
        for b in silent:
            site = await session.get(Site, b.site_id) if b.site_id else None
            managers = (await session.scalars(select(User.email).where(
                User.company_id == site.company_id, User.role == "manager", User.active.is_(True)))).all() if site else []
            rows.append((b, site, list(managers)))
        await session.commit()
    for b, site, managers in rows:
        where = f"{site.name}" if site else "an unassigned site"
        await audit.record("system", "box_silent", f"Box {b.serial} ({where}) hasn't checked in for "
                           f"{SILENT_MIN} minutes.", site.company_id if site else None, serial=b.serial)
        text = (f"The SiteSentry box at {where} ({b.serial}) hasn't contacted the portal for {SILENT_MIN} minutes. "
                f"Check that it has power and internet. Its safety rules keep running on site for up to "
                f"{LICENCE_DAYS} days.")
        await mail_overseers(f"SiteSentry: box at {where} is silent", text)
        await mailer.send(managers, f"SiteSentry: your box at {where} is silent", text)


async def watch_boxes():
    while True:
        try:
            await note_silent_boxes()
        except asyncio.CancelledError:
            raise
        except Exception as e:   # noqa: BLE001
            print(f"[Portal] Silent-box check failed: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(60)
