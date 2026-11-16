"""What happens on this box that the SiteSentry portal should know (docs/portal.md, "What a box reports"):
rules and zones changed, people and face photos added or removed, failed sign-ins, rule drives accepted or refused.
Never pictures, incidents or the names of the workers the cameras recognise.

note() queues an event in Redis; portal_link.py sends the queue with the next check-in and clears what the portal
took. Without PORTAL_URL nothing is queued. The portal keeps them in its tamper-evident security log and emails
the overseer about the suspicious ones (failed sign-ins, refused drives).
"""
import json
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis

QUEUE = "portal:events"
MAX_QUEUED = 500          # a box offline for days keeps the newest
ENABLED = bool(os.getenv("PORTAL_URL"))
_redis: aioredis.Redis | None = None


def init(redis_url: str):
    global _redis
    if ENABLED:
        _redis = aioredis.from_url(redis_url, decode_responses=True)


async def note(kind: str, summary: str, actor: str | None = None, **details):
    """kind: rule_changed | zone_changed | person_added | person_changed | face_photos | signin_failed |
    drive_accepted | drive_refused | summary_time. Never raises: reporting must not break the action itself."""
    if _redis is None:
        return
    event = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
             "actor": actor[:120] if actor else None,
             "summary": summary[:300], "details": details}
    try:
        await _redis.rpush(QUEUE, json.dumps(event, ensure_ascii=False))
        await _redis.ltrim(QUEUE, -MAX_QUEUED, -1)
    except Exception as e:   # noqa: BLE001
        print(f"[Portal] Couldn't queue an event for the portal: {e}", flush=True)


async def take(limit: int = 100) -> list[dict]:
    if _redis is None:
        return []
    raw = await _redis.lrange(QUEUE, 0, limit - 1)
    out = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except ValueError:
            pass
    return out


async def taken(count: int):
    """The portal has them: drop the first `count`."""
    if _redis is not None and count:
        await _redis.ltrim(QUEUE, count, -1)


async def close():
    if _redis is not None:
        await _redis.aclose()
