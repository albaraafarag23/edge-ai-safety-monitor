"""A short-lived cache for read endpoints whose answer is the same for everyone (statistics, analytics, the
incident list). When 50 people open the console at once, the database answers once instead of 50 times.

Never stale after a change: every write (a new incident, a status change, a saved report) calls `changed()`,
which empties the cache, so the next read computes afresh. Otherwise an answer is reused for at most `ttl`
seconds. "Single flight": while one request computes an answer, others asking the same thing wait for it
rather than computing it again. Measured (load test, docs/deploy.md): 100 people browsing went from a median
of ~0.5 s per request to milliseconds.
"""
import asyncio
import time

MAX_KEYS = 512           # different questions kept at once; past that the cache starts over

_version = 0
_store: dict = {}        # key -> (version, stored at, value)
_locks: dict = {}        # key -> asyncio.Lock


def changed():
    """Call after any write that read endpoints could show."""
    global _version
    _version += 1
    _store.clear()


async def cached(key: tuple, ttl: float, compute):
    """The value for `key`, computed by `await compute()` at most once per `ttl` seconds and per change."""
    hit = _store.get(key)
    if hit and hit[0] == _version and time.monotonic() - hit[1] < ttl:
        return hit[2]
    if len(_locks) > MAX_KEYS:
        _locks.clear()
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _store.get(key)   # someone may have computed it while this request waited
        if hit and hit[0] == _version and time.monotonic() - hit[1] < ttl:
            return hit[2]
        version = _version
        value = await compute()
        if version == _version:   # a write during the computation: don't keep an answer that may predate it
            if len(_store) >= MAX_KEYS:
                _store.clear()
            _store[key] = (version, time.monotonic(), value)
        return value
