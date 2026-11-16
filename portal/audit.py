"""The security log: who did what, as a hash chain.

Each entry's hash covers its own fields plus the previous entry's hash, so editing or deleting an old entry makes
every hash after it wrong, and verify() says where. (Someone with full database access could rewrite the whole
chain; the overseer's alert emails and Neon's backups are the outside copies that would show it.)
"""
import asyncio
import hashlib
import json
from datetime import timezone

from sqlalchemy import select

from models import AuditEntry, SessionLocal, User, now

GENESIS = "0" * 64
_lock = asyncio.Lock()   # one writer at a time, so two entries never claim the same predecessor


def _at(entry: AuditEntry) -> str:
    at = entry.at if entry.at.tzinfo else entry.at.replace(tzinfo=timezone.utc)   # SQLite drops the zone
    return at.astimezone(timezone.utc).isoformat(timespec="microseconds")


def entry_hash(entry: AuditEntry) -> str:
    body = json.dumps([entry.prev_hash, _at(entry), entry.actor_id, entry.actor, entry.action, entry.company_id,
                       entry.summary, entry.details], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


async def record(actor: User | str | None, action: str, summary: str, company_id: int | None = None,
                 **details) -> AuditEntry:
    """Adds one entry. `actor`: the signed-in person, or a label ("system", "command line")."""
    summary = summary[:-1] if summary.endswith("..") else summary   # a name ending in "." ("Nile Build Co.")
    async with _lock, SessionLocal() as session:
        prev = await session.scalar(select(AuditEntry.hash).order_by(AuditEntry.id.desc()).limit(1))
        entry = AuditEntry(at=now(), actor_id=actor.id if isinstance(actor, User) else None,
                           actor=actor.name if isinstance(actor, User) else (actor or "system"),
                           action=action, company_id=company_id, summary=summary, details=details,
                           prev_hash=prev or GENESIS)
        entry.hash = entry_hash(entry)
        session.add(entry)
        await session.commit()
        return entry


async def verify() -> dict:
    """{"ok": True, "entries": n} or {"ok": False, "broken_at": id} for the first entry that doesn't fit."""
    async with SessionLocal() as session:
        entries = (await session.scalars(select(AuditEntry).order_by(AuditEntry.id))).all()
    prev = GENESIS
    for entry in entries:
        if entry.prev_hash != prev or entry_hash(entry) != entry.hash:
            return {"ok": False, "entries": len(entries), "broken_at": entry.id}
        prev = entry.hash
    return {"ok": True, "entries": len(entries)}
