"""Dashboard sign-in: password hashing, session cookies, login rate limiting and the route guards.

A session is a signed token (user id, password fingerprint, expiry; HMAC-SHA256) in an HttpOnly
cookie. A cookie rather than an Authorization header because the browser sends it with every
request, including <img>, <video> and EventSource, which can't set headers. SameSite=Lax keeps
other sites from making signed-in POST/PATCH requests. The password fingerprint means changing or
resetting a password signs that user out everywhere; disabling a user takes effect on their next request.

Roles: admin (everything, including users), supervisor (handles incidents), viewer (read-only).

The ai_reporting service isn't a browser user: it sends INTERNAL_API_TOKEN in X-Internal-Token.
"""
import base64
import collections
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import func, select

from models import SessionLocal, User

COOKIE_NAME = "sm_session"
SESSION_HOURS = float(os.getenv("SESSION_HOURS", "12"))
# true behind HTTPS. Browsers also accept Secure cookies on http://localhost, so true works locally too.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
MIN_PASSWORD_LENGTH = 8

AUTH_SECRET = os.getenv("AUTH_SECRET", "")
if not AUTH_SECRET:
    AUTH_SECRET = secrets.token_hex(32)
    print("[Auth] AUTH_SECRET is not set: using a random one, so everyone is signed out when the backend restarts",
          flush=True)

ROLES = ("admin", "supervisor", "viewer")


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


def check_password_rules(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


# checked when the email doesn't exist, so a wrong email takes as long as a wrong password
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# ---------- login rate limiting ----------

class LoginLimiter:
    """At most `limit` failed sign-ins per key (an email or a client address) in WINDOW_S.

    In memory, so it resets when the backend restarts (one backend instance is assumed).
    Per email stops password guessing on one account even if the attacker changes address;
    per address stops one client from trying many accounts. The address limit is looser,
    because several people can share one address (an office network, or a proxy that hides them).
    """
    WINDOW_S = 15 * 60
    LIMITS = {"email": 5, "ip": 20}

    def __init__(self):
        self._failures: dict[str, collections.deque] = {}

    def _limit(self, key: str) -> int:
        return self.LIMITS.get(key.split(":", 1)[0], 5)

    def _recent(self, key: str, now: float) -> collections.deque:
        q = self._failures.setdefault(key, collections.deque())
        while q and q[0] < now - self.WINDOW_S:
            q.popleft()
        return q

    def retry_after(self, keys: list[str]) -> int:
        """Seconds until another attempt is allowed (0 = allowed now)."""
        now = time.time()
        wait = 0
        for key in keys:
            q = self._recent(key, now)
            if len(q) >= self._limit(key):
                wait = max(wait, int(q[0] + self.WINDOW_S - now) + 1)
        return wait

    def failed(self, keys: list[str]):
        now = time.time()
        for key in keys:
            self._recent(key, now).append(now)
        if len(self._failures) > 10_000:  # forget idle keys so memory stays bounded
            for key in [k for k, q in self._failures.items() if not q or q[-1] < now - self.WINDOW_S]:
                del self._failures[key]

    def succeeded(self, keys: list[str]):
        for key in keys:
            self._failures.pop(key, None)


login_limiter = LoginLimiter()


def client_address(request: Request) -> str:
    # nginx sets X-Real-IP; behind Tailscale Funnel the original client is first in X-Forwarded-For.
    # These headers can be forged, which only weakens the per-address limit, not the per-email one.
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")


# ---------- session tokens ----------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: str) -> str:
    return _b64(hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def _password_fingerprint(user: User) -> str:
    return _sign(user.password_hash)[:16]


def make_token(user: User) -> str:
    payload = _b64(json.dumps({"uid": user.id, "pv": _password_fingerprint(user),
                               "exp": int(time.time() + SESSION_HOURS * 3600)}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str | None) -> dict | None:
    """The claims of a valid, unexpired token, else None."""
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data


def set_session_cookie(response: Response, user: User):
    response.set_cookie(COOKIE_NAME, make_token(user), max_age=int(SESSION_HOURS * 3600), httponly=True,
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
        user = User(email=email.strip().lower(), name=name.strip(), role=role, password_hash=hash_password(password))
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
    claims = read_token(request.cookies.get(COOKIE_NAME))
    if claims:
        async with SessionLocal() as session:
            user = await session.get(User, claims.get("uid"))
        if user and user.active and hmac.compare_digest(claims.get("pv", ""), _password_fingerprint(user)):
            return user
    raise HTTPException(status_code=401, detail="Not signed in")


def require_role(*roles: str):
    async def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Your role doesn't allow this")
        return user
    return check


require_admin = require_role("admin")
can_handle_incidents = require_role("admin", "supervisor")


async def internal_service(request: Request):
    token = request.headers.get("X-Internal-Token", "")
    if not INTERNAL_API_TOKEN or not hmac.compare_digest(token, INTERNAL_API_TOKEN):
        raise HTTPException(status_code=401, detail="Internal endpoint")
