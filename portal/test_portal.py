"""Portal checks with a software passkey (a real P-256 key that signs exactly as a phone or laptop does).

    cd portal && python -m pytest -q test_portal.py
"""
import asyncio
import base64
import hashlib
import json
import os
import struct
import tempfile

DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ["PORTAL_URL"] = "http://localhost:8010"
os.environ.pop("OVERSEER_EMAIL", None)
for key in ("SMTP_HOST", "SMTP_USER", "SMTP_FROM"):
    os.environ.pop(key, None)

import httpx  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from webauthn.helpers import encode_cbor  # noqa: E402

import audit  # noqa: E402
import mailer  # noqa: E402
import main  # noqa: E402
from models import AuditEntry, SessionLocal, User, create_tables  # noqa: E402

ORIGIN = "http://localhost:8010"
RP_HASH = hashlib.sha256(b"localhost").digest()
SENT: list[tuple] = []


async def fake_send(to, subject, text):
    SENT.append((to, subject, text))
    return True

mailer.send = fake_send
main.mailer.send = fake_send


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SoftKey:
    """One passkey on one device."""
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.count = 0
        self.user_handle = b""

    def register(self, options: dict, origin: str = ORIGIN) -> dict:
        self.user_handle = unb64(options["user"]["id"])
        numbers = self.key.public_key().public_numbers()
        cose = encode_cbor({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
        auth_data = (RP_HASH + bytes([0x45]) + struct.pack(">I", 0) + b"\0" * 16
                     + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose)
        client = json.dumps({"type": "webauthn.create", "challenge": options["challenge"], "origin": origin}).encode()
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(client),
                             "attestationObject": b64(encode_cbor({"fmt": "none", "attStmt": {}, "authData": auth_data}))},
                "clientExtensionResults": {}}

    def sign(self, options: dict, origin: str = ORIGIN) -> dict:
        self.count += 1
        auth_data = RP_HASH + bytes([0x05]) + struct.pack(">I", self.count)
        client = json.dumps({"type": "webauthn.get", "challenge": options["challenge"], "origin": origin}).encode()
        signature = self.key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64(self.cred_id), "rawId": b64(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64(client), "authenticatorData": b64(auth_data),
                             "signature": b64(signature), "userHandle": b64(self.user_handle)},
                "clientExtensionResults": {}}


def browser() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=ORIGIN,
                             headers={"Origin": ORIGIN})


async def accept(client, link: str, key: SoftKey, label="Test laptop"):
    secret = link.rsplit("/", 1)[1]
    r = await client.post(f"/api/invites/{secret}/options")
    if r.status_code != 200:   # a used or unknown link is refused before the passkey step
        return r
    opts = r.json()
    return await client.post(f"/api/invites/{secret}", json={"id": opts["id"], "credential": key.register(opts["options"]),
                                                             "label": label})


async def sign_in(client, key: SoftKey):
    opts = (await client.post("/api/auth/signin/options")).json()
    return await client.post("/api/auth/signin", json={"id": opts["id"], "credential": key.sign(opts["options"])})


async def step_up(client, key: SoftKey):
    opts = (await client.post("/api/auth/stepup/options")).json()
    r = await client.post("/api/auth/stepup", json={"id": opts["id"], "credential": key.sign(opts["options"])})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def loop():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(create_tables())
    yield loop
    loop.close()
    os.unlink(DB)


def run(loop, coro):
    return loop.run_until_complete(coro)


def test_whole_flow(loop):
    async def flow():
        # the first overseer, set up from the command-line style link
        os.environ["OVERSEER_EMAIL"] = "boss@example.com"
        await main.bootstrap_overseer()
        async with SessionLocal() as s:
            from sqlalchemy import select
            boss = await s.scalar(select(User).where(User.email == "boss@example.com"))
        assert boss and boss.role == "overseer"
        link = await main.new_invite(boss, None)

        laptop = SoftKey()
        o = browser()
        assert (await o.get("/api/auth/me")).status_code == 401
        r = await accept(o, link, laptop)
        assert r.status_code == 200, r.text
        me = (await o.get("/api/auth/me")).json()
        assert me["role"] == "overseer" and me["device"]["status"] == "approved"

        # the link is single use
        assert (await accept(browser(), link, SoftKey())).status_code == 410
        # a passkey made for another address is refused
        secret2 = (await main.new_invite(boss, None)).rsplit("/", 1)[1]
        c = browser()
        opts = (await c.post(f"/api/invites/{secret2}/options")).json()
        r = await c.post(f"/api/invites/{secret2}", json={"id": opts["id"],
                                                          "credential": SoftKey().register(opts["options"], "https://evil.example")})
        assert r.status_code == 400

        # sign out, sign in again with the passkey; the overseer is emailed about it
        await o.post("/api/auth/signout")
        assert (await o.get("/api/auth/me")).status_code == 401
        SENT.clear()
        assert (await sign_in(o, laptop)).status_code == 200
        assert any("overseer sign-in" in s[1] for s in SENT)

        # changes from another site are refused
        evil = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=ORIGIN,
                                 headers={"Origin": "https://evil.example"}, cookies=o.cookies)
        assert (await evil.post("/api/companies", json={"name": "X"})).status_code == 403

        # a company: needs a recent passkey check (fresh from sign-in, so it works now)
        r = await o.post("/api/companies", json={"name": "Nile Build"})
        assert r.status_code == 200, r.text
        company = r.json()["id"]
        assert (await o.post("/api/companies", json={"name": "nile build"})).status_code == 409
        site = (await o.post(f"/api/companies/{company}/sites", json={"name": "New Capital", "city": "Cairo"})).json()
        r = await o.post(f"/api/companies/{company}/people", json={"email": "Karim@Nile.example", "name": "Karim",
                                                                    "role": "manager", "site_ids": [site["id"]]})
        assert r.status_code == 200, r.text
        manager_link = r.json()["invite_link"]
        assert r.json()["email"] == "karim@nile.example"

        # the passkey again once the last check is old
        async with SessionLocal() as s:
            from sqlalchemy import update
            from models import Session as S
            from datetime import timedelta
            from models import now
            await s.execute(update(S).values(verified_at=now() - timedelta(minutes=10)))
            await s.commit()
        r = await o.post("/api/companies", json={"name": "Delta Hospital"})
        assert r.status_code == 428 and r.json()["detail"] == "step_up"
        await step_up(o, laptop)
        assert (await o.post("/api/companies", json={"name": "Delta Hospital"})).status_code == 200

        # the manager sets up their phone from the link and adds a supervisor; can't add a manager
        phone = SoftKey()
        m = browser()
        assert (await accept(m, manager_link, phone, "Phone")).status_code == 200
        assert (await m.post(f"/api/companies/{company}/people", json={"email": "m2@nile.example", "name": "Mona",
                                                                        "role": "manager"})).status_code == 403
        r = await m.post(f"/api/companies/{company}/people", json={"email": "omar@nile.example", "name": "Omar",
                                                                    "role": "supervisor", "site_ids": [site["id"]]})
        assert r.status_code == 200, r.text
        omar_link = r.json()["invite_link"]
        # a manager sees only their own company
        assert [c["name"] for c in (await m.get("/api/companies")).json()] == ["Nile Build"]
        other = [c for c in (await o.get("/api/companies")).json() if c["name"] == "Delta Hospital"][0]["id"]
        assert (await m.get(f"/api/companies/{other}")).status_code == 404
        assert (await m.get("/api/overview")).status_code == 403

        # Omar sets up his phone; later asks to add a second device: waits for his manager
        omar_phone, omar_laptop = SoftKey(), SoftKey()
        s1 = browser()
        assert (await accept(s1, omar_link, omar_phone)).status_code == 200
        n = browser()
        opts = (await n.post("/api/devices/request/options", json={"email": "omar@nile.example"})).json()
        SENT.clear()
        r = await n.post("/api/devices/request", json={"id": opts["id"], "credential": omar_laptop.register(opts["options"]),
                                                       "label": "Omar's laptop"})
        assert r.json() == {"status": "pending"}
        assert any("karim@nile.example" in s[0] for s in SENT)   # his manager is asked
        r = await sign_in(n, omar_laptop)
        assert r.status_code == 403 and r.json()["detail"] == "device_pending"

        # an unknown email gets the same answer and creates nothing
        opts = (await n.post("/api/devices/request/options", json={"email": "nobody@x.example"})).json()
        r = await n.post("/api/devices/request", json={"id": opts["id"], "credential": SoftKey().register(opts["options"])})
        assert r.json() == {"status": "pending"}

        # the manager approves it (the overseer could too); then it signs in
        pending = (await m.get("/api/approvals")).json()
        assert [p["label"] for p in pending] == ["Omar's laptop"]
        r = await m.post(f"/api/devices/{pending[0]['id']}/decision", json={"decision": "approve"})
        assert r.status_code == 200, r.text
        assert (await sign_in(n, omar_laptop)).status_code == 200
        # a supervisor can't approve or add people
        assert (await n.get("/api/approvals")).status_code == 403
        assert (await n.post(f"/api/companies/{company}/people", json={"email": "v@nile.example", "name": "Vera",
                                                                        "role": "viewer"})).status_code == 403

        # removing a device signs it out at once
        r = await m.post(f"/api/devices/{pending[0]['id']}/decision", json={"decision": "revoke"})
        assert r.status_code == 200
        assert (await n.get("/api/auth/me")).status_code == 401
        assert (await sign_in(n, omar_laptop)).json()["detail"] == "device_revoked"

        # a manager's new device is the overseer's to approve, not another manager's
        karim_laptop = SoftKey()
        opts = (await n.post("/api/devices/request/options", json={"email": "karim@nile.example"})).json()
        await n.post("/api/devices/request", json={"id": opts["id"], "credential": karim_laptop.register(opts["options"])})
        assert (await m.get("/api/approvals")).json() == []
        assert len((await o.get("/api/approvals")).json()) == 1
        assert (await o.get("/api/overview")).json()["approvals"][0]["person"]["email"] == "karim@nile.example"

        # suspending the company signs its people out
        r = await o.patch(f"/api/companies/{company}", json={"active": False})
        assert r.status_code == 200
        assert (await m.get("/api/auth/me")).status_code == 401
        assert (await sign_in(m, phone)).json()["detail"] == "account_off"

        # the log is a chain; changing an old entry breaks it
        log = (await o.get("/api/audit")).json()
        assert log["chain"]["ok"] and log["chain"]["entries"] >= 10
        async with SessionLocal() as s:
            entry = await s.get(AuditEntry, 2)
            entry.summary = "nothing happened"
            await s.commit()
        assert (await audit.verify()) == {"ok": False, "entries": log["chain"]["entries"], "broken_at": 2}

    run(loop, flow())
