"""SiteSentry portal: one place for the overseer (every client) and for each client's people (their sites).

Run locally:  uvicorn main:app --port 8010   (SQLite in ./portal.db unless DATABASE_URL is set)
The screens are the frontend's portal build (frontend: npm run build:portal), served from PORTAL_UI_DIR.
API under /api. Boxes connect in step 3 (docs/portal.md).
"""
import asyncio
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from webauthn.helpers import generate_user_handle

import audit
import boxes as box_link
import mailer
import security as sec
from models import (AuditEntry, Box, Company, Device, Invite, Site, User, UserSite, SessionLocal, create_tables,
                    now)
from security import Signed, aware, can_manage, fresh, roles, sha, signed_in

INVITE_HOURS = 72
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
BOX_SILENT_MIN = 10


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await bootstrap_overseer()
    await box_link.portal_key()
    watcher = asyncio.create_task(box_link.watch_boxes())
    yield
    watcher.cancel()


app = FastAPI(title="SiteSentry portal", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
api = APIRouter(prefix="/api", dependencies=[Depends(sec.same_origin)])


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if sec.COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health():
    return {"ok": True}


# ---------- shapes ----------

def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "company_id": u.company_id,
            "active": u.active, "last_sign_in": aware(u.last_sign_in), "created_at": aware(u.created_at)}


def device_dict(d: Device) -> dict:
    return {"id": d.id, "user_id": d.user_id, "label": d.label, "status": d.status,
            "created_at": aware(d.created_at), "last_used": aware(d.last_used), "decided_at": aware(d.decided_at)}


def box_dict(b: Box) -> dict:
    last = aware(b.last_checkin)
    silent = b.status == "approved" and (not last or last < now() - timedelta(minutes=BOX_SILENT_MIN))
    return {"id": b.id, "serial": b.serial, "site_id": b.site_id, "status": b.status, "last_checkin": last,
            "silent": silent, "health": b.health or {}, "plugins": b.plugins or [], "connected": bool(b.console_url)}


def label_from(request: Request, given: str | None) -> str:
    """A short name for the device, from what the screen sends (browser + system) or the User-Agent."""
    text = (given or request.headers.get("user-agent") or "A device").strip()
    return re.sub(r"\s+", " ", text)[:120]


def check_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL.match(value):
        raise ValueError("That doesn't look like an email address")
    return value


# ---------- first overseer ----------

async def new_invite(user: User, by: User | None) -> str:
    """A one-time link for `user` to register a device (older unused links stop working)."""
    secret = secrets.token_urlsafe(32)
    async with SessionLocal() as session:
        await session.execute(update(Invite).where(Invite.user_id == user.id, Invite.used_at.is_(None))
                              .values(expires_at=now()))
        session.add(Invite(token_hash=sha(secret), user_id=user.id, created_by=by.id if by else None,
                           expires_at=now() + timedelta(hours=INVITE_HOURS)))
        await session.commit()
    return f"{sec.PORTAL_URL}/invite/{secret}"


async def bootstrap_overseer():
    """First start (or every overseer device lost): OVERSEER_EMAIL gets an account and a setup link in the server
    log, valid INVITE_HOURS. Once the overseer has an approved device, nothing is printed."""
    email = (os.getenv("OVERSEER_EMAIL") or "").strip().lower()
    if not email:
        return
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user and user.role != "overseer":
            print(f"[Portal] OVERSEER_EMAIL belongs to a {user.role}; not changing it", flush=True)
            return
        if user and await session.scalar(select(func.count()).select_from(Device).where(
                Device.user_id == user.id, Device.status == "approved")):
            return
        if user and await session.scalar(select(func.count()).select_from(Invite).where(
                Invite.user_id == user.id, Invite.used_at.is_(None), Invite.expires_at > now())):
            print("[Portal] The overseer's setup link is still waiting to be used (see the earlier log line, or "
                  "run `python manage.py invite <email>` for a new one)", flush=True)
            return
        if not user:
            user = User(email=email, name=os.getenv("OVERSEER_NAME") or "Overseer", role="overseer",
                        handle=generate_user_handle())
            session.add(user)
            await session.commit()
    link = await new_invite(user, None)
    await audit.record("system", "overseer_setup_link", f"A setup link was made for the overseer ({email}).")
    print(f"[Portal] Overseer setup link (one use, {INVITE_HOURS} h): {link}", flush=True)


# ---------- signing in ----------

class CeremonyIn(BaseModel):
    id: str = Field(max_length=64)
    credential: dict
    label: str | None = Field(None, max_length=200)


async def me_dict(me: Signed) -> dict:
    return {**user_dict(me.user), "company": {"id": me.company.id, "name": me.company.name} if me.company else None,
            "device": device_dict(me.device), "fresh": me.fresh}


@api.get("/auth/me")
async def who_am_i(me: Signed = Depends(signed_in)):
    return await me_dict(me)


@api.post("/auth/signin/options")
async def signin_options(request: Request):
    sec.limit(request, "signin", 40)
    return await sec.authentication_options("signin")


@api.post("/auth/signin")
async def signin(body: CeremonyIn, request: Request, response: Response):
    sec.limit(request, "signin", 40)
    challenge = await sec.take_challenge(body.id, "signin")
    device, user = await sec.check_assertion(challenge, body.credential)
    async with SessionLocal() as session:
        company = await session.get(Company, user.company_id) if user.company_id else None
    if device.status != "approved":
        await audit.record(user, "signin_refused", f"{user.name} tried to sign in from a device that is "
                           f"{device.status} ({device.label}).", user.company_id, device_id=device.id)
        raise HTTPException(status_code=403, detail=f"device_{device.status}")
    if not user.active or (company and not company.active):
        await audit.record(user, "signin_refused", f"{user.name} tried to sign in but their account or company "
                           "is switched off.", user.company_id)
        raise HTTPException(status_code=403, detail="account_off")
    await sec.start_session(response, user, device)
    await audit.record(user, "signin", f"{user.name} signed in ({device.label}).", user.company_id,
                       device_id=device.id, address=sec.client_address(request))
    if user.role == "overseer":   # the overseer hears about every overseer sign-in
        await mailer.send(user.email, "SiteSentry: overseer sign-in",
                          f"Someone signed in to the SiteSentry portal as overseer ({user.email}) at "
                          f"{now():%Y-%m-%d %H:%M} UTC from {device.label} "
                          f"({sec.client_address(request)}).\n\nIf this wasn't you, sign in from another device "
                          f"and revoke this one under My devices.")
    return {"ok": True}


@api.post("/auth/signout")
async def signout(request: Request, response: Response):
    await sec.end_session(request, response)
    return {"ok": True}


@api.post("/auth/stepup/options")
async def stepup_options(me: Signed = Depends(signed_in)):
    return await sec.authentication_options("stepup", allow=[me.device.credential_id])


@api.post("/auth/stepup")
async def stepup(body: CeremonyIn, request: Request, me: Signed = Depends(signed_in)):
    challenge = await sec.take_challenge(body.id, "stepup")
    device, user = await sec.check_assertion(challenge, body.credential)
    if device.id != me.device.id:
        raise HTTPException(status_code=403, detail="Use the passkey on this device")
    await sec.mark_fresh(request.cookies.get(sec.COOKIE))
    return {"ok": True}


# ---------- invite links: a new person's first device ----------

async def _invite(secret: str) -> tuple[Invite, User, Company | None]:
    async with SessionLocal() as session:
        invite = await session.scalar(select(Invite).where(Invite.token_hash == sha(secret)))
        user = await session.get(User, invite.user_id) if invite else None
        company = await session.get(Company, user.company_id) if user and user.company_id else None
    if not invite or not user or not user.active:
        raise HTTPException(status_code=404, detail="invite_unknown")
    if invite.used_at or aware(invite.expires_at) < now():
        raise HTTPException(status_code=410, detail="invite_used")
    return invite, user, company


@api.get("/invites/{secret}")
async def read_invite(secret: str, request: Request):
    sec.limit(request, "invite", 60)
    invite, user, company = await _invite(secret)
    return {"name": user.name, "email": user.email, "role": user.role,
            "company": company.name if company else None, "expires_at": aware(invite.expires_at)}


@api.post("/invites/{secret}/options")
async def invite_options(secret: str, request: Request):
    sec.limit(request, "invite", 60)
    _, user, _ = await _invite(secret)
    return await sec.registration_options(user.handle, user.email, user.name, invite=sha(secret))


@api.post("/invites/{secret}")
async def accept_invite(secret: str, body: CeremonyIn, request: Request, response: Response):
    sec.limit(request, "invite", 60)
    invite, user, _ = await _invite(secret)
    challenge = await sec.take_challenge(body.id, "register")
    if challenge.data.get("invite") != sha(secret):
        raise HTTPException(status_code=400, detail="That took too long or was already used. Try again.")
    verified = sec.check_registration(challenge, body.credential)
    async with SessionLocal() as session:
        row = await session.get(Invite, invite.id)
        if row.used_at:   # two tabs racing on one link
            raise HTTPException(status_code=410, detail="invite_used")
        row.used_at = now()
        device = Device(user_id=user.id, credential_id=verified.credential_id, public_key=verified.credential_public_key,
                        sign_count=verified.sign_count, label=label_from(request, body.label), status="approved",
                        decided_by=invite.created_by, decided_at=now())
        session.add(device)
        await session.commit()
    await audit.record(user, "device_added", f"{user.name} set up their first device with an invite link "
                       f"({device.label}).", user.company_id, device_id=device.id)
    await sec.start_session(response, user, device)
    return {"ok": True}


# ---------- a new device for someone who already has one ----------

class DeviceRequestIn(BaseModel):
    email: str = Field(max_length=254)
    name_check: str | None = None   # unused; keeps the shape open

    @field_validator("email")
    @classmethod
    def valid(cls, v):
        return check_email(v)


@api.post("/devices/request/options")
async def device_request_options(body: DeviceRequestIn, request: Request):
    """Same answer for any email, so nobody can find out who has an account here."""
    sec.limit(request, "device-request", 10)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == body.email))
        existing = (await session.scalars(select(Device.credential_id).where(Device.user_id == user.id))).all() \
            if user else []
    handle = user.handle if user else generate_user_handle()
    return await sec.registration_options(handle, body.email, user.name if user else body.email, existing,
                                          requested_for=body.email)


async def approvers_of(user: User) -> list[str]:
    """Who gets the 'please approve this device' email."""
    async with SessionLocal() as session:
        overseers = (await session.scalars(select(User.email).where(User.role == "overseer",
                                                                    User.active.is_(True)))).all()
        if user.role in ("supervisor", "viewer"):
            managers = (await session.scalars(select(User.email).where(
                User.role == "manager", User.company_id == user.company_id, User.active.is_(True)))).all()
            return list(managers) or list(overseers)
    return list(overseers)


@api.post("/devices/request")
async def device_request(body: CeremonyIn, request: Request):
    sec.limit(request, "device-request", 10)
    challenge = await sec.take_challenge(body.id, "register")
    email = challenge.data.get("requested_for")
    if not email:
        raise HTTPException(status_code=400, detail="That took too long or was already used. Try again.")
    verified = sec.check_registration(challenge, body.credential)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user and user.active:
            pending = await session.scalar(select(func.count()).select_from(Device).where(
                Device.user_id == user.id, Device.status == "pending"))
            if pending < 3:   # a few waiting at most, so the approval list can't be flooded
                device = Device(user_id=user.id, credential_id=verified.credential_id,
                                public_key=verified.credential_public_key, sign_count=verified.sign_count,
                                label=label_from(request, body.label), status="pending")
                session.add(device)
                await session.commit()
                await audit.record(user, "device_requested", f"{user.name} asked to add a new device "
                                   f"({device.label}).", user.company_id, device_id=device.id)
                await mailer.send(await approvers_of(user), f"SiteSentry: {user.name} wants to add a device",
                                  f"{user.name} ({user.email}) asked to sign in from a new device: {device.label}.\n\n"
                                  f"Approve or refuse it in the portal: {sec.PORTAL_URL}/approvals\n\n"
                                  "If you don't know about this, refuse it.")
    return {"status": "pending"}


# ---------- approvals, my devices ----------

@api.get("/approvals")
async def approvals(me: Signed = Depends(roles("overseer", "manager"))):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Device, User).join(User, User.id == Device.user_id)
                                      .where(Device.status == "pending").order_by(Device.created_at))).all()
        companies = {c.id: c.name for c in (await session.scalars(select(Company))).all()}
    return [{**device_dict(d), "person": user_dict(u), "company": companies.get(u.company_id)}
            for d, u in rows if can_manage(me.user, u)]


class DecisionIn(BaseModel):
    decision: Literal["approve", "refuse", "revoke"]


@api.post("/devices/{device_id}/decision")
async def decide(device_id: int, body: DecisionIn, me: Signed = Depends(fresh)):
    async with SessionLocal() as session:
        device = await session.get(Device, device_id)
        owner = await session.get(User, device.user_id) if device else None
        if not device or not owner:
            raise HTTPException(status_code=404, detail="No such device")
        own = owner.id == me.user.id
        if body.decision == "revoke":
            if not (own or can_manage(me.user, owner)):
                raise HTTPException(status_code=403, detail="You can't do that")
            if device.id == me.device.id:
                raise HTTPException(status_code=409, detail="Sign in on another device to remove this one")
        elif not can_manage(me.user, owner) or own and me.user.role != "overseer":
            raise HTTPException(status_code=403, detail="You can't do that")
        if body.decision in ("approve", "refuse") and device.status != "pending":
            raise HTTPException(status_code=409, detail="This device was already decided")
        device.status = {"approve": "approved", "refuse": "refused", "revoke": "revoked"}[body.decision]
        device.decided_by, device.decided_at = me.user.id, now()
        await session.commit()
    if device.status != "approved":
        await sec.sign_out_everywhere(device_id=device.id)
    verb = {"approved": "approved", "refused": "refused", "revoked": "removed"}[device.status]
    await audit.record(me.user, f"device_{device.status}", f"{me.user.name} {verb} {owner.name}'s device "
                       f"({device.label}).", owner.company_id, device_id=device.id)
    return device_dict(device)


@api.get("/me/devices")
async def my_devices(me: Signed = Depends(signed_in)):
    async with SessionLocal() as session:
        rows = (await session.scalars(select(Device).where(Device.user_id == me.user.id)
                                      .order_by(Device.created_at))).all()
    return [{**device_dict(d), "this": d.id == me.device.id} for d in rows]


# ---------- companies, sites, people ----------

class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CompanyPatch(BaseModel):
    active: bool


class SiteIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    city: str | None = Field(None, max_length=120)


class PersonIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(min_length=2, max_length=120)
    role: Literal["manager", "supervisor", "viewer"]
    site_ids: list[int] = []

    @field_validator("email")
    @classmethod
    def valid(cls, v):
        return check_email(v)


class PersonPatch(BaseModel):
    active: bool | None = None
    site_ids: list[int] | None = None


def company_guard(me: Signed, company_id: int):
    if me.user.role != "overseer" and me.user.company_id != company_id:
        raise HTTPException(status_code=404, detail="No such company")


@api.get("/companies")
async def companies(me: Signed = Depends(signed_in)):
    async with SessionLocal() as session:
        query = select(Company).order_by(Company.name)
        if me.user.role != "overseer":
            query = query.where(Company.id == me.user.company_id)
        rows = (await session.scalars(query)).all()
        sites = (await session.scalars(select(Site))).all()
        people = (await session.execute(select(User.company_id, func.count()).group_by(User.company_id))).all()
        boxes = (await session.scalars(select(Box))).all()
    per_people = dict(people)
    site_company = {s.id: s.company_id for s in sites}
    out = []
    for c in rows:
        own_boxes = [b for b in boxes if site_company.get(b.site_id) == c.id]
        out.append({"id": c.id, "name": c.name, "active": c.active, "created_at": aware(c.created_at),
                    "sites": sum(1 for s in sites if s.company_id == c.id), "people": per_people.get(c.id, 0),
                    "boxes": len(own_boxes), "silent_boxes": sum(1 for b in own_boxes if box_dict(b)["silent"])})
    return out


@api.post("/companies")
async def add_company(body: CompanyIn, me: Signed = Depends(fresh)):
    if me.user.role != "overseer":
        raise HTTPException(status_code=403, detail="You can't do that")
    async with SessionLocal() as session:
        if await session.scalar(select(Company).where(func.lower(Company.name) == body.name.strip().lower())):
            raise HTTPException(status_code=409, detail="A company with this name already exists")
        company = Company(name=body.name.strip())
        session.add(company)
        await session.commit()
    await audit.record(me.user, "company_added", f"{me.user.name} added the company {company.name}.", company.id)
    return {"id": company.id, "name": company.name}


@api.get("/companies/{company_id}")
async def company_detail(company_id: int, me: Signed = Depends(signed_in)):
    company_guard(me, company_id)
    async with SessionLocal() as session:
        company = await session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="No such company")
        sites = (await session.scalars(select(Site).where(Site.company_id == company_id).order_by(Site.name))).all()
        people = (await session.scalars(select(User).where(User.company_id == company_id).order_by(User.name))).all()
        links = (await session.scalars(select(UserSite).where(UserSite.user_id.in_([p.id for p in people])))).all()
        devices = (await session.scalars(select(Device).where(Device.user_id.in_([p.id for p in people])))).all()
        boxes = (await session.scalars(select(Box).where(Box.site_id.in_([s.id for s in sites])))).all()
        invites = (await session.scalars(select(Invite).where(Invite.user_id.in_([p.id for p in people]),
                                                              Invite.used_at.is_(None),
                                                              Invite.expires_at > now()))).all()
    if me.user.role not in ("overseer", "manager"):   # supervisors and viewers: their sites, no people list
        mine = {link.site_id for link in links if link.user_id == me.user.id}
        return {"id": company.id, "name": company.name, "active": company.active, "people": [],
                "sites": [{"id": s.id, "name": s.name, "city": s.city} for s in sites if s.id in mine],
                "boxes": [box_dict(b) for b in boxes if b.site_id in mine]}
    waiting = {i.user_id for i in invites}
    return {
        "id": company.id, "name": company.name, "active": company.active, "created_at": aware(company.created_at),
        "sites": [{"id": s.id, "name": s.name, "city": s.city} for s in sites],
        "boxes": [box_dict(b) for b in boxes],
        "people": [{**user_dict(p), "site_ids": [link.site_id for link in links if link.user_id == p.id],
                    "devices": [device_dict(d) for d in devices if d.user_id == p.id],
                    "invite_waiting": p.id in waiting, "can_manage": can_manage(me.user, p)} for p in people],
    }


@api.patch("/companies/{company_id}")
async def change_company(company_id: int, body: CompanyPatch, me: Signed = Depends(fresh)):
    if me.user.role != "overseer":
        raise HTTPException(status_code=403, detail="You can't do that")
    async with SessionLocal() as session:
        company = await session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="No such company")
        company.active = body.active
        member_ids = (await session.scalars(select(User.id).where(User.company_id == company_id))).all()
        await session.commit()
    if not body.active:
        for uid in member_ids:
            await sec.sign_out_everywhere(user_id=uid)
    await audit.record(me.user, "company_" + ("resumed" if body.active else "suspended"),
                       f"{me.user.name} {'switched back on' if body.active else 'suspended'} {company.name}.",
                       company.id)
    return {"id": company.id, "active": company.active}


@api.post("/companies/{company_id}/sites")
async def add_site(company_id: int, body: SiteIn, me: Signed = Depends(fresh)):
    company_guard(me, company_id)
    if me.user.role not in ("overseer", "manager"):
        raise HTTPException(status_code=403, detail="You can't do that")
    async with SessionLocal() as session:
        if not await session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="No such company")
        if await session.scalar(select(Site).where(Site.company_id == company_id,
                                                   func.lower(Site.name) == body.name.strip().lower())):
            raise HTTPException(status_code=409, detail="This company already has a site with that name")
        site = Site(company_id=company_id, name=body.name.strip(), city=(body.city or "").strip() or None)
        session.add(site)
        await session.commit()
    await audit.record(me.user, "site_added", f"{me.user.name} added the site {site.name}.", company_id)
    return {"id": site.id, "name": site.name, "city": site.city}


async def _check_sites(company_id: int, site_ids: list[int]):
    if not site_ids:
        return
    async with SessionLocal() as session:
        found = (await session.scalars(select(Site.id).where(Site.id.in_(site_ids),
                                                             Site.company_id == company_id))).all()
    if set(found) != set(site_ids):
        raise HTTPException(status_code=400, detail="Those sites aren't all this company's")


@api.post("/companies/{company_id}/people")
async def add_person(company_id: int, body: PersonIn, me: Signed = Depends(fresh)):
    company_guard(me, company_id)
    if me.user.role == "manager" and body.role == "manager":
        raise HTTPException(status_code=403, detail="Only the overseer adds managers")
    if me.user.role not in ("overseer", "manager"):
        raise HTTPException(status_code=403, detail="You can't do that")
    await _check_sites(company_id, body.site_ids)
    async with SessionLocal() as session:
        company = await session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="No such company")
        if await session.scalar(select(User).where(User.email == body.email)):
            raise HTTPException(status_code=409, detail="Someone with this email already has an account")
        person = User(email=body.email, name=body.name.strip(), role=body.role, company_id=company_id,
                      handle=generate_user_handle())
        session.add(person)
        await session.flush()
        session.add_all([UserSite(user_id=person.id, site_id=s) for s in set(body.site_ids)])
        await session.commit()
    link = await new_invite(person, me.user)
    emailed = await mailer.send(person.email, "Your SiteSentry account",
                                f"Hello {person.name},\n\n{me.user.name} added you to SiteSentry for {company.name}.\n\n"
                                f"Open this link on your phone or laptop to set up your sign-in (one use, "
                                f"{INVITE_HOURS} hours):\n{link}\n\nYou'll use your fingerprint, face or screen lock; "
                                "there's no password.")
    await audit.record(me.user, "person_added", f"{me.user.name} added {person.name} as {person.role}.",
                       company_id, person_id=person.id)
    return {**user_dict(person), "invite_link": link, "emailed": emailed}


@api.post("/people/{person_id}/invite")
async def reinvite(person_id: int, me: Signed = Depends(fresh)):
    async with SessionLocal() as session:
        person = await session.get(User, person_id)
    if not person or not can_manage(me.user, person) or person.id == me.user.id:
        raise HTTPException(status_code=404, detail="No such person")
    link = await new_invite(person, me.user)
    emailed = await mailer.send(person.email, "Your SiteSentry sign-in link",
                                f"Hello {person.name},\n\nHere is a new link to set up your SiteSentry sign-in "
                                f"(one use, {INVITE_HOURS} hours):\n{link}")
    await audit.record(me.user, "invite_link", f"{me.user.name} made a new sign-in link for {person.name}.",
                       person.company_id, person_id=person.id)
    return {"invite_link": link, "emailed": emailed}


@api.patch("/people/{person_id}")
async def change_person(person_id: int, body: PersonPatch, me: Signed = Depends(fresh)):
    async with SessionLocal() as session:
        person = await session.get(User, person_id)
        if not person or not can_manage(me.user, person) or person.id == me.user.id:
            raise HTTPException(status_code=404, detail="No such person")
        if body.site_ids is not None:
            await _check_sites(person.company_id, body.site_ids)
            for link in (await session.scalars(select(UserSite).where(UserSite.user_id == person.id))).all():
                await session.delete(link)
            session.add_all([UserSite(user_id=person.id, site_id=s) for s in set(body.site_ids)])
        if body.active is not None:
            person.active = body.active
        await session.commit()
    if body.active is False:
        await sec.sign_out_everywhere(user_id=person.id)
    what = "switched off" if body.active is False else "switched back on" if body.active else "changed the sites of"
    await audit.record(me.user, "person_changed", f"{me.user.name} {what} {person.name}.", person.company_id,
                       person_id=person.id)
    return user_dict(person)


# ---------- overview, boxes, log ----------

@api.get("/overview")
async def overview(me: Signed = Depends(roles("overseer"))):
    async with SessionLocal() as session:
        boxes = (await session.scalars(select(Box))).all()
        company_count = await session.scalar(select(func.count()).select_from(Company))
    pending = await approvals(me)
    shaped = [box_dict(b) for b in boxes]
    return {"companies": company_count, "boxes": len(shaped),
            "boxes_fine": sum(1 for b in shaped if b["status"] == "approved" and not b["silent"]),
            "silent": [b for b in shaped if b["silent"]],
            "boxes_waiting": [b for b in shaped if b["status"] == "waiting"],
            "approvals": pending}


@api.get("/boxes")
async def boxes(me: Signed = Depends(roles("overseer"))):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Box, Site, Company).outerjoin(Site, Site.id == Box.site_id)
                                      .outerjoin(Company, Company.id == Site.company_id))).all()
    return [{**box_dict(b), "site": s.name if s else None, "company": c.name if c else None,
             "company_id": c.id if c else None} for b, s, c in rows]


@api.get("/audit")
async def audit_log(limit: int = 100, me: Signed = Depends(roles("overseer", "manager"))):
    async with SessionLocal() as session:
        query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(min(max(limit, 1), 500))
        if me.user.role == "manager":
            query = query.where(AuditEntry.company_id == me.user.company_id)
        rows = (await session.scalars(query)).all()
    chain = await audit.verify() if me.user.role == "overseer" else None
    return {"chain": chain, "entries": [{"id": e.id, "at": aware(e.at), "actor": e.actor, "action": e.action,
                                         "summary": e.summary} for e in rows]}


app.include_router(api)
app.include_router(box_link.router, dependencies=[Depends(sec.same_origin)])
app.include_router(box_link.box_api)   # boxes sign each request with their own key instead


# ---------- the screens (frontend portal build) ----------

UI_DIR = Path(os.getenv("PORTAL_UI_DIR", Path(__file__).parent / "ui"))


@app.get("/{path:path}", include_in_schema=False)
async def screens(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    file = (UI_DIR / path).resolve()
    if path and file.is_file() and UI_DIR.resolve() in file.parents:
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        return FileResponse(file, headers={"Cache-Control": cache})
    index = UI_DIR / "portal.html"
    if not index.is_file():
        return Response("The portal screens aren't built yet (frontend: npm run build:portal).", media_type="text/plain")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
