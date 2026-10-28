"""Synthetic tests for the two-zone demo plugin (plugins/construction_demo.json). No Redis needed.

    cd event_engine && python test_demo_plugin.py

No-entry area on the left of the picture, work area on the right (hard hat and vest checked only there),
at the camera's 1920x1080. A person counts as inside when their feet are inside.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rules import RuleEngine

PLUGIN = json.loads((Path(__file__).parent.parent / "plugins" / "construction_demo.json").read_text())
T0 = datetime(2026, 10, 29, 10, 0, 0, tzinfo=timezone.utc)
FRAME = [1920, 1080]


def person(x, y_feet=1000, w=200, h=700, hardhat=True, vest=True):
    """A person whose box starts at x, with whatever they wear (or the NO- box when they don't)."""
    objects = [{"class_name": "Person", "confidence": 0.9, "bbox": [x, y_feet - h, x + w, y_feet]}]
    head = [x + 60, y_feet - h, x + 140, y_feet - h + 80]
    body = [x + 20, y_feet - h + 150, x + 180, y_feet - h + 400]
    objects.append({"class_name": "Hardhat" if hardhat else "NO-Hardhat", "confidence": 0.9, "bbox": head})
    objects.append({"class_name": "Safety Vest" if vest else "NO-Safety Vest", "confidence": 0.9, "bbox": body})
    return objects


def run(objects, seconds=5, fps=2, zones=None):
    """Same objects for `seconds`; returns the rule ids that fired. zones: drawn in the console (fractions)."""
    engine = RuleEngine({PLUGIN["plugin_id"]: PLUGIN})
    if zones:
        engine.zones[PLUGIN["plugin_id"]] = zones
    fired = []
    for i in range(int(seconds * fps)):
        event = {"timestamp": (T0 + timedelta(seconds=i / fps)).isoformat(), "camera_id": "cam_01", "frame_id": i,
                 "plugin_id": PLUGIN["plugin_id"], "detections": objects, "frame_size": FRAME}
        fired += [inc["metadata"]["rule_id"] for inc in engine.process(event)]
    return sorted(set(fired))


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))
    return cond


results = []
LEFT, MIDDLE, RIGHT = 200, 800, 1500   # box x: no-entry area, between the zones, work area

f = run(person(LEFT))
results.append(check("No-entry: anyone inside fires, even with full PPE", f == ["RULE_ZONE_01"], f))
f = run(person(LEFT, hardhat=False, vest=False))
results.append(check("No-entry: PPE isn't checked there", f == ["RULE_ZONE_01"], f))

results.append(check("Work area: full PPE is fine", not run(person(RIGHT))))
f = run(person(RIGHT, hardhat=False))
results.append(check("Work area: no hard hat fires", f == ["RULE_PPE_01"], f))
f = run(person(RIGHT, vest=False))
results.append(check("Work area: no vest fires", f == ["RULE_PPE_02"], f))
f = run(person(RIGHT, hardhat=False, vest=False))
results.append(check("Work area: neither fires both", f == ["RULE_PPE_01", "RULE_PPE_02"], f))
results.append(check("Work area: under 3 s doesn't fire yet", not run(person(RIGHT, hardhat=False), seconds=2)))

results.append(check("Between the zones: nothing fires, even without PPE",
                     not run(person(MIDDLE, hardhat=False, vest=False))))

f = run([{"class_name": "smoking", "confidence": 0.9, "bbox": [840, 300, 1000, 460]}] + person(MIDDLE))
results.append(check("Other rules as usual: smoking fires anywhere", f == ["RULE_SMOKE_01"], f))

# zones redrawn on the website: swap the two sides
swapped = {"no_entry": [[0.6, 0], [1, 0], [1, 1], [0.6, 1]], "work_area": [[0, 0], [0.3, 0], [0.3, 1], [0, 1]]}
f = run(person(RIGHT, hardhat=False), zones=swapped)
results.append(check("Redrawn: the right side is now no-entry", f == ["RULE_ZONE_01"], f))
f = run(person(LEFT, hardhat=False), zones=swapped)
results.append(check("Redrawn: the left side now checks PPE", f == ["RULE_PPE_01"], f))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
