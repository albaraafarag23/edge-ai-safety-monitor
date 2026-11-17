"""FallWatch (falls.py): person down judged over time. Run: python test_falls.py"""
from falls import FallWatch

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail}")


STANDING = [900, 300, 1000, 700]   # a person, upright (100 x 400)
DOWN = [800, 620, 1200, 720]       # the same person lying where they stood (400 x 100)
TRUCK = [100, 500, 600, 800]       # a parked truck the detector likes
STEP = 0.4                         # one check every 0.4 s (every 4th frame at ~10 checks/s, roughly)


def run(w, t0, seconds, candidates, people=()):
    out, t = [], t0
    while t < t0 + seconds - 1e-9:
        w.note_people(t, list(people))
        out = w.update(t, candidates(t) if callable(candidates) else candidates)
        t += STEP
    return out, t


# 1. a seen fall: standing, then lying at the same spot, confirmed every check
w = FallWatch()
_, t = run(w, 0.0, 2.0, [], people=[STANDING])
first, t = run(w, t, 0.5, [(DOWN, True)])
check("One confirmed check is not enough to call someone down", first == [], first)
out, t = run(w, t, 1.5, [(DOWN, True)])
check("A few confirmed checks in a row: the person is down", len(out) == 1, out)
check("  and the fall was seen (an upright person stood there just before)", out and out[0]["fell"] is True, out)
out, t = run(w, t, 10.0, [(DOWN, True)])
check("  and down_s keeps counting while they stay down", out and out[0]["down_s"] >= 9, out)

# 2. the same box with nobody standing there before: down, but no fall seen
w = FallWatch()
out, _ = run(w, 0.0, 3.0, [(DOWN, True)])
check("Someone found already lying is down, fell = False", len(out) == 1 and out[0]["fell"] is False, out)

# 3. a parked truck the check confirms only now and then (1 in 3): never down
w = FallWatch()
out, _ = run(w, 0.0, 30.0, lambda t: [(TRUCK, round(t / STEP) % 3 == 0)])
check("A box confirmed only 1 check in 3 is never down", out == [], out)

# 4. a real fall where the check misses 1 in 3 checks: still down (majority)
w = FallWatch()
_, t = run(w, 0.0, 2.0, [], people=[STANDING])
out, _ = run(w, t, 4.0, lambda t: [(DOWN, round(t / STEP) % 3 != 0)])
check("A real fall the check misses 1 time in 3 is still down", len(out) == 1 and out[0]["fell"], out)

# 5. the detector loses the person for a moment: they stay down, down_s doesn't restart
w = FallWatch()
out, t = run(w, 0.0, 5.0, [(DOWN, True)])
before = out[0]["down_s"] if out else None
_, t = run(w, t, 0.8, [])           # two checks without the box
out, t = run(w, t, 1.2, [(DOWN, True)])
check("A short gap keeps them down and down_s goes on", out and before is not None and out[0]["down_s"] > before, (before, out))

# 6. they get up: no longer down after the window empties of yes votes
w = FallWatch()
_, t = run(w, 0.0, 4.0, [(DOWN, True)])
out, t = run(w, t, 3.5, [(DOWN, False)])
check("When the check says no for a few seconds they are no longer down", out == [], out)

# 7. a person standing far away when someone else lies down does not make it a seen fall
w = FallWatch()
FAR = [100, 100, 200, 500]
_, t = run(w, 0.0, 2.0, [], people=[FAR])
out, _ = run(w, t, 3.0, [(DOWN, True)])
check("An upright person elsewhere in the picture is not a seen fall", out and out[0]["fell"] is False, out)

# 8. standing too long ago (more than LOOKBACK_S before) is not a seen fall
w = FallWatch()
_, t = run(w, 0.0, 1.0, [], people=[STANDING])
_, t = run(w, t, 6.0, [])
out, _ = run(w, t, 3.0, [(DOWN, True)])
check("Someone who stood there 6 s before is not a seen fall", out and out[0]["fell"] is False, out)

# 9. two people down at once are followed separately
w = FallWatch()
OTHER = [1300, 620, 1700, 720]
out, _ = run(w, 0.0, 3.0, [(DOWN, True), (OTHER, True)])
check("Two people down at once are two separate reports", len(out) == 2, out)

print(f"\n{passed}/{passed + failed} passed")
raise SystemExit(1 if failed else 0)
