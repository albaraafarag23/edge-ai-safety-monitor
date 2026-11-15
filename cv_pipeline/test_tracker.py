"""Checks for the person tracker. No camera or model needed.

    cd cv_pipeline && python test_tracker.py
"""
from tracker import Tracker

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")


def box(x, y=100, w=80, h=200):
    return [x, y, x + w, y + h]


t = Tracker()
ids, _ = t.update([box(100), box(600)], 0.0)
check("Two people get two different numbers", ids == [1, 2], f"{ids}")
ids, _ = t.update([box(620), box(110)], 0.1)
check("They keep their numbers when they move, whatever order the detector lists them in", ids == [2, 1], f"{ids}")
for i in range(1, 20):   # walking right, 15 px a frame
    ids, _ = t.update([box(110 + 15 * i), box(620)], 0.1 + i * 0.07)
check("A walking person keeps the number", ids == [1, 2], f"{ids}")
ids, _ = t.update([box(620)], 2.0)
ids, gone = t.update([box(620)], 2.5)
check("Someone who left is not confused with who stays", ids == [2])
ids, gone = t.update([box(620)], 4.0)
check("A person gone for a while is forgotten", gone == [1] or 1 not in t._tracks, f"{gone}")
ids, _ = t.update([box(620), box(100)], 4.1)
check("A newcomer gets a new number", ids == [2, 3], f"{ids}")
ids, _ = t.update([box(630), box(640, w=82)], 4.2)   # two boxes over the same person: only one can be them
check("Overlapping boxes never share a number", len(set(ids)) == 2, f"{ids}")
ids, _ = t.update([], 4.3)
check("An empty frame is fine", ids == [])

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
