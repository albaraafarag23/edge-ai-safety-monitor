"""Retry queue for alert emails and report saves that failed (network down, SMTP or backend unavailable).

Jobs live in a Redis sorted set scored by the next attempt time, so they survive a restart of this service
(and of Redis, which keeps an append-only file). Each failure doubles the wait, up to RETRY_MAX_WAIT_S;
a job older than RETRY_GIVE_UP_S is dropped and its report is marked "failed" for good.

    job = {"kind": "email" | "report", "event_id": ..., "attempts": 1, "first_failed": <unix time>, ...}
"""
import json
import os
import time

KEY = "ai_reporting:outbox"
RETRY_FIRST_WAIT_S = float(os.getenv("RETRY_FIRST_WAIT_S", "30"))
RETRY_MAX_WAIT_S = float(os.getenv("RETRY_MAX_WAIT_S", "900"))
RETRY_GIVE_UP_S = float(os.getenv("RETRY_GIVE_UP_S", str(24 * 3600)))


def next_wait(attempts: int) -> float:
    return min(RETRY_FIRST_WAIT_S * 2 ** (attempts - 1), RETRY_MAX_WAIT_S)


def add(r, job: dict, now: float | None = None):
    """Queue a job after a failure. `job` holds what's needed to try again; attempts/first_failed are set here."""
    now = time.time() if now is None else now
    job = {**job, "attempts": job.get("attempts", 0) + 1, "first_failed": job.get("first_failed", now)}
    r.zadd(KEY, {json.dumps(job, sort_keys=True): now + next_wait(job["attempts"])})
    return job


def take_due(r, now: float | None = None, limit: int = 10) -> list[dict]:
    """Removes and returns the jobs whose time has come."""
    now = time.time() if now is None else now
    members = r.zrangebyscore(KEY, "-inf", now, start=0, num=limit)
    jobs = []
    for m in members:
        if r.zrem(KEY, m):  # only the caller that removed it handles it
            jobs.append(json.loads(m))
    return jobs


def expired(job: dict, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    return now - job["first_failed"] >= RETRY_GIVE_UP_S


def pending(r) -> int:
    return r.zcard(KEY)
