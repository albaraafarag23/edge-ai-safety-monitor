"""Sign-in plumbing: passkey ceremonies, sessions, who may do what, and the passkey-again check.

PORTAL_URL is the address people open (https://... in the cloud, http://localhost:8010 locally). Passkeys are
bound to its host name: a passkey made for one address never works on another, which is what makes them
phishing-proof. Changing the address later means everyone registers their devices again.
"""
import collections
import hashlib
import os
import secrets
import time
from datetime import timedelta, timezone
from urllib.parse import urlsplit

import webauthn
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from webauthn.helpers import options_to_json_dict
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

from models import Challenge, Company, Device, Session, SessionLocal, User, now

PORTAL_URL = os.getenv("PORTAL_URL", "http://localhost:8010").rstrip("/")
RP_ID = urlsplit(PORTAL_URL).hostname or "localhost"
RP_NAME = "SiteSentry"
COOKIE = "portal_session"
COOKIE_SECURE = PORTAL_URL.startswith("https://")
SESSION_HOURS = float(os.getenv("SESSION_HOURS", "12"))
STEP_UP_MINUTES = 5          # dangerous changes need a passkey check this recent
CHALLENGE_MINUTES = 5


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)   # SQLite drops the zone


# ---------- rate limit (per client address; one server instance) ----------

_hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)


def client_address(request: Request) -> str:
    # the proxy in front (Tailscale Funnel, Render) appends the address it saw; anything before it came from the
    # visitor and could be made up, so the last entry is the one to trust
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[-1].strip() or (request.client.host if request.client else "?")


def limit(request: Request, bucket: str, per_15_min: int):
    key = f"{bucket}:{client_address(request)}"
    hits, cutoff = _hits[key], time.monotonic() - 900
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) >= per_15_min:
        raise HTTPException(status_code=429, detail="Too many tries. Wait a few minutes and try again.")
    hits.append(time.monotonic())


# ---------- same-site check on every change (with SameSite=Lax cookies, belt and braces) ----------

async def same_origin(request: Request):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if urlsplit(origin).netloc != urlsplit(PORTAL_URL).netloc:
        raise HTTPException(status_code=403, detail="Request from another site refused")


# ---------- passkey ceremonies ----------

async def _new_challenge(purpose: str, challenge: bytes, **data) -> str:
    cid = secrets.token_urlsafe(24)
    async with SessionLocal() as session:
        await session.execute(delete(Challenge).where(Challenge.expires_at < now()))
        session.add(Challenge(id=cid, challenge=challenge, purpose=purpose, data=data,
                              expires_at=now() + timedelta(minutes=CHALLENGE_MINUTES)))
        await session.commit()
    return cid


async def take_challenge(cid: str, purpose: str) -> Challenge:
    """One use only: the challenge is deleted as it is read."""
    async with SessionLocal() as session:
        row = await session.get(Challenge, cid or "")
        if row:
            await session.delete(row)
            await session.commit()
    if not row or row.purpose != purpose or aware(row.expires_at) < now():
        raise HTTPException(status_code=400, detail="That took too long or was already used. Try again.")
    return row


async def registration_options(user_handle: bytes, email: str, name: str, exclude: list[bytes] = (),
                               **data) -> dict:
    options = webauthn.generate_registration_options(
        rp_id=RP_ID, rp_name=RP_NAME, user_id=user_handle, user_name=email, user_display_name=name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,          # signs in without typing the email
            user_verification=UserVerificationRequirement.REQUIRED),   # fingerprint / face / PIN, not just a tap
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in exclude])
    cid = await _new_challenge("register", options.challenge, **data)
    return {"id": cid, "options": options_to_json_dict(options)}


def check_registration(challenge: Challenge, credential: dict):
    try:
        return webauthn.verify_registration_response(
            credential=credential, expected_challenge=challenge.challenge, expected_rp_id=RP_ID,
            expected_origin=PORTAL_URL, require_user_verification=True)
    except Exception as e:   # noqa: BLE001 (the library raises several kinds)
        raise HTTPException(status_code=400, detail=f"The passkey couldn't be checked ({type(e).__name__})")


async def authentication_options(purpose: str, allow: list[bytes] = ()) -> dict:
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID, allow_credentials=[PublicKeyCredentialDescriptor(id=c) for c in allow],
        user_verification=UserVerificationRequirement.REQUIRED)
    cid = await _new_challenge(purpose, options.challenge)
    return {"id": cid, "options": options_to_json_dict(options)}


async def check_assertion(challenge: Challenge, credential: dict) -> tuple[Device, User]:
    """The signed-in-with passkey: its device and person, after the signature checks out. Any device status."""
    try:
        cred_id = webauthn.helpers.base64url_to_bytes(credential.get("rawId") or credential.get("id") or "")
    except Exception:   # noqa: BLE001
        raise HTTPException(status_code=400, detail="That passkey isn't one this portal knows")
    async with SessionLocal() as session:
        device = await session.scalar(select(Device).where(Device.credential_id == cred_id))
        if not device:
            raise HTTPException(status_code=401, detail="That passkey isn't one this portal knows")
        try:
            verified = webauthn.verify_authentication_response(
                credential=credential, expected_challenge=challenge.challenge, expected_rp_id=RP_ID,
                expected_origin=PORTAL_URL, credential_public_key=device.public_key,
                credential_current_sign_count=device.sign_count, require_user_verification=True)
        except Exception as e:   # noqa: BLE001
            raise HTTPException(status_code=401, detail=f"The passkey check failed ({type(e).__name__})")
        device.sign_count = verified.new_sign_count
        await session.commit()
        user = await session.get(User, device.user_id)
    return device, user


# ---------- sessions ----------

async def start_session(response: Response, user: User, device: Device):
    token = secrets.token_urlsafe(32)
    async with SessionLocal() as session:
        await session.execute(delete(Session).where(Session.expires_at < now()))
        session.add(Session(token_hash=sha(token), user_id=user.id, device_id=device.id,
                            expires_at=now() + timedelta(hours=SESSION_HOURS)))
        u, d = await session.get(User, user.id), await session.get(Device, device.id)
        u.last_sign_in = d.last_used = now()
        await session.commit()
    response.set_cookie(COOKIE, token, max_age=int(SESSION_HOURS * 3600), httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, path="/")


async def end_session(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        async with SessionLocal() as session:
            await session.execute(delete(Session).where(Session.token_hash == sha(token)))
            await session.commit()
    response.delete_cookie(COOKIE, path="/")


class Signed:
    """The person behind a request, with their device and session."""
    def __init__(self, user: User, device: Device, session: Session, company: Company | None):
        self.user, self.device, self.session, self.company = user, device, session, company

    @property
    def fresh(self) -> bool:
        return aware(self.session.verified_at) > now() - timedelta(minutes=STEP_UP_MINUTES)


async def signed_in(request: Request) -> Signed:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with SessionLocal() as session:
        row = await session.get(Session, sha(token))
        if not row or aware(row.expires_at) < now():
            raise HTTPException(status_code=401, detail="Not signed in")
        user, device = await session.get(User, row.user_id), await session.get(Device, row.device_id)
        company = await session.get(Company, user.company_id) if user and user.company_id else None
    if not user or not user.active or not device or device.status != "approved" or (company and not company.active):
        raise HTTPException(status_code=401, detail="Not signed in")
    return Signed(user, device, row, company)


def roles(*allowed: str):
    async def check(me: Signed = Depends(signed_in)) -> Signed:
        if me.user.role not in allowed:
            raise HTTPException(status_code=403, detail="You can't do that")
        return me
    return check


async def fresh(me: Signed = Depends(signed_in)) -> Signed:
    """Dangerous changes: the passkey again if the last check is older than STEP_UP_MINUTES. The screen sees
    428 + step_up, asks for the passkey (/api/auth/stepup), and repeats the request."""
    if not me.fresh:
        raise HTTPException(status_code=428, detail="step_up")
    return me


async def mark_fresh(session_token: str):
    async with SessionLocal() as session:
        row = await session.get(Session, sha(session_token))
        if row:
            row.verified_at = now()
            await session.commit()


async def sign_out_everywhere(user_id: int | None = None, device_id: int | None = None):
    async with SessionLocal() as session:
        if device_id is not None:
            await session.execute(delete(Session).where(Session.device_id == device_id))
        if user_id is not None:
            await session.execute(delete(Session).where(Session.user_id == user_id))
        await session.commit()


def can_manage(actor: User, target: User) -> bool:
    """May `actor` approve `target`'s devices, re-invite or switch them off? Overseer: anyone. A manager: their
    own company's supervisors and viewers (managers' devices are the overseer's to approve)."""
    if actor.role == "overseer":
        return True
    return (actor.role == "manager" and target.company_id == actor.company_id
            and target.role in ("supervisor", "viewer"))
