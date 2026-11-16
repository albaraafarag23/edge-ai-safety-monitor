"""The drive loader's licence decisions (Lock 2).   python3 test_licence.py"""
import json
import sys
import time
import types

if "redis" not in sys.modules:   # the decisions don't talk to Redis: a stand-in module is enough to import main
    try:
        import redis  # noqa: F401
    except ImportError:
        stub = types.ModuleType("redis")
        stub.exceptions = types.SimpleNamespace(RedisError=type("RedisError", (Exception,), {}))
        stub.from_url = lambda *a, **k: None
        sys.modules["redis"] = stub

import main  # noqa: E402

ok = bad = 0


def check(name, cond):
    global ok, bad
    ok += bool(cond)
    bad += not cond
    print(("PASS " if cond else "FAIL ") + name)


class FakeRedis:
    def __init__(self, licence):
        self.value = None if licence is None else json.dumps(licence)

    def get(self, key):
        return self.value


soon = time.time() + 3600
good = {"plugins": ["construction_safety"], "cancelled_drives": ["LOST-0001"], "valid_until": soon}

main.LICENCE_REQUIRED = False
check("no licence needed, no licence: runs", main.licence_problem(FakeRedis(None), "construction_safety") is None)
check("a cancelled drive is refused even when no licence is needed",
      main.licence_problem(FakeRedis(good), "construction_safety", "LOST-0001") == "drive_cancelled")
check("another drive is fine", main.licence_problem(FakeRedis(good), "construction_safety", "OK-0002") is None)

main.LICENCE_REQUIRED = True
check("licence needed, none yet: refused", main.licence_problem(FakeRedis(None), "construction_safety") == "no_licence")
check("licensed rule set: runs", main.licence_problem(FakeRedis(good), "construction_safety", "OK-0002") is None)
check("rule set not on the licence: refused",
      main.licence_problem(FakeRedis(good), "hospital_safety", "OK-0002") == "not_licensed")
check("licence ran out (7 days without the portal): refused",
      main.licence_problem(FakeRedis({**good, "valid_until": time.time() - 1}), "construction_safety") == "licence_expired")
check("cancelled beats everything", main.licence_problem(FakeRedis(good), "construction_safety", "LOST-0001")
      == "drive_cancelled")
check("garbage in Redis counts as no licence",
      main.licence_problem(type("R", (), {"get": lambda self, k: "{not json"})(), "construction_safety") == "no_licence")

print(f"{ok}/{ok + bad} passed")
raise SystemExit(bad > 0)
