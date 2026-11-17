"""Synthetic tests for the hospital plugin (plugins/hospital_safety.json). No Redis needed.

    cd event_engine && python test_hospital_plugin.py

Medication store on the left of the picture, isolation room on the right (mask and gown checked only there),
at the camera's 1920x1080. A person counts as inside when their feet are inside. The plugin uses the same rule
types as construction: only the file is new.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rules import RuleEngine, usable

PLUGIN = json.loads((Path(__file__).parent.parent / "plugins" / "hospital_safety.json").read_text())
T0 = datetime(2026, 11, 16, 10, 0, 0, tzinfo=timezone.utc)
ISOLATION_X, STORE_X, CORRIDOR_X = 1300, 100, 650


def person(x, mask=True, gown=True, gloves=True, eyes="Goggles", track=1, y_feet=1000, w=200, h=700):
    """A person whose box starts at x, with the mask, gown, gloves and eye protection the model found on them
    (eyes: "Goggles", "Face Shield" or None)."""
    objects = [{"class_name": "Person", "confidence": 0.9, "bbox": [x, y_feet - h, x + w, y_feet],
                "attributes": {"track_id": track}}]
    if mask:
        objects.append({"class_name": "Mask", "confidence": 0.9, "bbox": [x + 70, y_feet - h + 40, x + 130, y_feet - h + 90]})
    if gown:
        objects.append({"class_name": "Coverall", "confidence": 0.9, "bbox": [x + 10, y_feet - h + 110, x + 190, y_feet - 20]})
    if gloves:
        objects.append({"class_name": "Gloves", "confidence": 0.9, "bbox": [x + 5, y_feet - h + 380, x + 45, y_feet - h + 430]})
    if eyes:
        objects.append({"class_name": eyes, "confidence": 0.9, "bbox": [x + 65, y_feet - h + 15, x + 135, y_feet - h + 45]})
    return objects


def run(objects, seconds=8, fps=2):
    engine = RuleEngine({PLUGIN["plugin_id"]: PLUGIN})
    fired = []
    for i in range(int(seconds * fps)):
        fired += engine.process({"timestamp": (T0 + timedelta(seconds=i / fps)).isoformat(), "camera_id": "cam_01",
                                 "frame_id": i, "plugin_id": PLUGIN["plugin_id"], "detections": objects,
                                 "frame_size": [1920, 1080]})
    return fired, engine


def rules_of(fired):
    return sorted({i["metadata"]["rule_id"] for i in fired})


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


f, _ = run(person(ISOLATION_X))
check("Isolation room: mask and gown on, nothing fires", rules_of(f) == [], rules_of(f))
f, e = run(person(ISOLATION_X, mask=False))
check("Isolation room: no mask fires the mask rule only", rules_of(f) == ["RULE_MASK_01"], rules_of(f))
check("  and it is a PPE incident that says what is missing",
      f[0]["event_type"] == "PPE_MISSING" and f[0]["metadata"]["missing_equipment"] == ["mask"]
      and f[0]["location"] == "Isolation room")
check("  and the live picture is told this person lacks a mask", e.missing_now["cam_01"] == {"1": ["mask"]}, e.missing_now)
f, _ = run(person(ISOLATION_X, gown=False))
check("Isolation room: no gown fires the gown rule only", rules_of(f) == ["RULE_GOWN_01"], rules_of(f))
f, _ = run(person(ISOLATION_X, mask=False, gown=False))
check("Isolation room: neither fires both", rules_of(f) == ["RULE_GOWN_01", "RULE_MASK_01"], rules_of(f))
f, _ = run(person(CORRIDOR_X, mask=False, gown=False))
check("Corridor: no mask or gown is fine outside the isolation room", rules_of(f) == [], rules_of(f))
f, _ = run(person(ISOLATION_X, mask=False), seconds=2)
check("A missing mask for under 3 seconds is not an incident", rules_of(f) == [], rules_of(f))
f, _ = run(person(STORE_X))
check("Medication store: entering fires, even fully dressed", rules_of(f) == ["RULE_ZONE_01"], rules_of(f))
three = sum((person(1000 + 220 * n, track=n) for n in range(3)), [])
four = sum((person(960 + 220 * n, track=n) for n in range(4)), [])
check("Isolation room: three people is within the limit", rules_of(run(three)[0]) == [], rules_of(run(three)[0]))
f, _ = run(four)
check("Isolation room: a fourth person is over capacity", rules_of(f) == ["RULE_ZONE_02"], rules_of(f))
check("  and nobody in particular is counted for it", f[0]["metadata"]["violators"] == [])
smoker = person(CORRIDOR_X) + [{"class_name": "smoking", "confidence": 0.9, "bbox": [660, 300, 840, 520]}]
f, _ = run(smoker)
check("Smoking anywhere in the building fires", rules_of(f) == ["RULE_SMOKE_01"] and f[0]["severity"] == "HIGH", rules_of(f))
off = {r["rule_id"] for r in PLUGIN["rules"] if not usable(r)}
check("Only patient fall is listed but not in use yet", off == {"RULE_POSE_01"}, off)
f, _ = run(person(ISOLATION_X, gloves=False))
check("Isolation room: no gloves fires the gloves rule", rules_of(f) == ["RULE_GLOVES_01"], rules_of(f))
f, _ = run(person(ISOLATION_X, eyes=None))
check("Isolation room: no goggles or face shield fires the eye rule", rules_of(f) == ["RULE_EYES_01"], rules_of(f))
f, _ = run(person(ISOLATION_X, eyes="Face Shield"))
check("A face shield counts as eye protection", rules_of(f) == [], rules_of(f))
f, _ = run(person(CORRIDOR_X, gloves=False, eyes=None))
check("Gloves and eye protection are only checked in the isolation room", rules_of(f) == [], rules_of(f))
ar = PLUGIN["translations"]["ar"]
check("Every rule, zone and item has its Arabic text",
      set(ar["rules"]) == {r["rule_id"] for r in PLUGIN["rules"]} and set(ar["zones"]) == set(PLUGIN["zones"])
      and {i["name"] for r in PLUGIN["rules"] for i in r.get("required", [])} <= set(ar["items"])
      and all(len(ar["rules"][r["rule_id"]]["recommended_actions"]) == len(r["recommended_actions"]) for r in PLUGIN["rules"]))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
