"""Dashboard sign-in: password hashing, session cookies and the route guards.

A session is a signed token (user id + expiry, HMAC-SHA256) in an HttpOnly cookie. A cookie
rather than an Authorization header because the browser sends it with every request, including
<img>, <video> and EventSource, which can't set headers. SameSite=Lax keeps other sites from
making signed-in POST/PATCH requests.

The ai_reporting service isn't a browser user: it sends INTERNAL_API_TOKEN in X-Internal-Token.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime

from fastapi import HTTPException, Request, Response
from sqlalchemy import func, select

from models import SessionLocal, User

COOKIE_NAME = "sm_session"
SESSION_HOURS = float(os.getenv("SESSION_HOURS", "12"))
# true behind HTTPS; on plain http://localhost the browser would drop a Secure cookie
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

AUTH_SECRET = os.getenv("AUTH_SECRET", "")
if not AUTH_SECRET:
    AUTH_SECRET = secrets.token_hex(32)
    print("[Auth] AUTH_SECRET is not set: using a random one, so everyone is signed out when the backend restarts",
          flush=True)

ROLES = ("admin", "supervisor")


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, key = stored.split("$")
        if algo != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), key)


# checked when the email doesn't exist, so a wrong email takes as long as a wrong password
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# ---------- session tokens ----------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: str) -> str:
    return _b64(hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def make_token(user_id: int) -> str:
    payload = _b64(json.dumps({"uid": user_id, "exp": int(time.time() + SESSION_HOURS * 3600)}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str | None) -> int | None:
    """The user id in a valid, unexpired token, else None."""
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("uid")


def set_session_cookie(response: Response, user_id: int):
    response.set_cookie(COOKIE_NAME, make_token(user_id), max_age=int(SESSION_HOURS * 3600), httponly=True,
                        samesite="lax", secure=COOKIE_SECURE, path="/")


def clear_session_cookie(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=COOKIE_SECURE)


# ---------- users ----------

async def authenticate(email: str, password: str) -> User | None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email.strip().lower()))
        if not user or not user.active:
            verify_password(password, _DUMMY_HASH)
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login_at = datetime.utcnow()
        await session.commit()
        return user


async def create_user(email: str, name: str, password: str, role: str = "supervisor") -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    async with SessionLocal() as session:
        user = User(email=email.strip().lower(), name=name, role=role, password_hash=hash_password(password))
        session.add(user)
        await session.commit()
        return user


async def ensure_admin():
    """First start: create the admin account from ADMIN_EMAIL / ADMIN_PASSWORD so someone can sign in."""
    async with SessionLocal() as session:
        if await session.scalar(select(func.count()).select_from(User)):
            return
    email = os.getenv("ADMIN_EMAIL") or "admin@example.com"
    password = os.getenv("ADMIN_PASSWORD") or ""
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    await create_user(email, os.getenv("ADMIN_NAME") or "Site Admin", password, "admin")
    print(f"[Auth] Created the first admin account: {email}", flush=True)
    if generated:
        print(f"[Auth] ADMIN_PASSWORD is not set; generated password: {password}  (shown once)", flush=True)


# ---------- route guards (FastAPI dependencies) ----------

async def current_user(request: Request) -> User:
    user_id = read_token(request.cookies.get(COOKIE_NAME))
    if user_id is not None:
        async with SessionLocal() as session:
            user = await session.get(User, user_id)
        if user and user.active:
            return user
    raise HTTPException(status_code=401, detail="Not signed in")


async def internal_service(request: Request):
    token = request.headers.get("X-Internal-Token", "")
    if not INTERNAL_API_TOKEN or not hmac.compare_digest(token, INTERNAL_API_TOKEN):
        raise HTTPException(status_code=401, detail="Internal endpoint")
