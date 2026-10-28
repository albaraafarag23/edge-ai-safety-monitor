"""Synthetic tests for the rule engine. No Redis needed.

    cd event_engine && python test_rules.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rules import RuleEngine

PLUGIN = json.loads((Path(__file__).parent.parent / "plugins" / "construction_safety.json").read_text())
T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)

# Worker standing at x=300-400 (feet at y=400 -> inside crane_swing_area only)
WORKER = {"class_name": "Person", "confidence": 0.9, "bbox": [300, 120, 400, 400]}
HARDHAT = {"class_name": "Hardhat", "confidence": 0.9, "bbox": [325, 120, 375, 160]}
NO_HARDHAT = {"class_name": "NO-Hardhat", "confidence": 0.9, "bbox": [325, 120, 375, 160]}
VEST = {"class_name": "Safety Vest", "confidence": 0.9, "bbox": [310, 180, 390, 280]}


def person_at(x, y_feet, h=200):
    return {"class_name": "Person", "confidence": 0.9, "bbox": [x, y_feet - h, x + 60, y_feet]}


def run(frames, camera="cam_01", rules=None, fps=2, settings=None, start=T0, site_tz="UTC"):
    """frames: list of object lists, one per frame. Returns [(frame_index, incident), ...].
    settings: console rule settings {rule_id: {...}}, or a function i -> settings from frame i."""
    plugin = dict(PLUGIN)
    if rules is not None:
        plugin["rules"] = [r for r in PLUGIN["rules"] if r["rule_id"] in rules]
    engine = RuleEngine({plugin["plugin_id"]: plugin}, site_tz=site_tz)
    fired = []
    for i, objects in enumerate(frames):
        if settings:
            engine.settings[plugin["plugin_id"]] = settings(i) if callable(settings) else settings
        event = {"timestamp": (start + timedelta(seconds=i / fps)).isoformat(), "camera_id": camera,
                 "frame_id": i, "plugin_id": plugin["plugin_id"], "detections": objects}
        fired += [(i, inc) for inc in engine.process(event)]
    return fired


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))
    return cond


results = []

# --- PPE ---
f = run([[WORKER, NO_HARDHAT, VEST]] * 10, rules=["RULE_PPE_01"])  # 5 s at 2 fps
results.append(check("PPE: NO-Hardhat fires once, after 3 s", len(f) == 1 and f[0][0] == 6, f"{[i for i, _ in f]}"))
results.append(check("PPE: reports hard_hat missing",
                     f and f[0][1]["metadata"]["missing_equipment"] == ["hard_hat"]))
results.append(check("PPE: duration_seconds recorded", f and f[0][1]["duration_seconds"] == 3.0))

f = run([[WORKER, HARDHAT, VEST]] * 10, rules=["RULE_PPE_01"])
results.append(check("PPE: fully equipped worker never fires", not f))

f = run([[WORKER, VEST]] * 10, rules=["RULE_PPE_01"])
results.append(check("PPE: no helmet detected at all counts as missing",
                     f and f[0][1]["metadata"]["missing_equipment"] == ["hard_hat"]))

f = run([[WORKER]] * 10, rules=["RULE_PPE_01", "RULE_PPE_02"])
results.append(check("PPE: hard hat and vest are separate rules, both fire",
                     sorted(m for _, i in f for m in i["metadata"]["missing_equipment"]) == ["hard_hat", "safety_vest"]))
f = run([[WORKER, HARDHAT]] * 10, rules=["RULE_PPE_01", "RULE_PPE_02"])
results.append(check("PPE: vest missing only fires the vest rule",
                     [i["metadata"]["rule_id"] for _, i in f] == ["RULE_PPE_02"]))

bad = [WORKER, NO_HARDHAT, VEST]
f = run([bad] * 4 + [[]] + [bad] * 3, rules=["RULE_PPE_01"])  # 0.5 s dropout
results.append(check("PPE: short detector dropout doesn't reset the timer", len(f) == 1))
f = run([bad] * 4 + [[]] * 4 + [bad] * 5, rules=["RULE_PPE_01"])  # 2 s gap
results.append(check("PPE: long gap resets the timer", not f))

# --- incident payload matches docs/contracts.md ---
inc = f[0][1] if (f := run([[WORKER, NO_HARDHAT, VEST]] * 8, rules=["RULE_PPE_01"])) else {}
expected = {"event_id", "timestamp", "plugin_id", "camera_id", "severity", "event_type", "location",
            "duration_seconds", "rules_violated", "snapshot_url", "clip_url", "metadata"}
results.append(check("Contract: incident has exactly the contract fields", set(inc) == expected,
                     f"extra {set(inc) - expected}, missing {expected - set(inc)}"))
results.append(check("Contract: event_id looks like evt_xxx", str(inc.get("event_id", "")).startswith("evt_")))
results.append(check("Contract: no zone -> location NOT SPECIFIED", inc.get("location") == "NOT SPECIFIED"))
results.append(check("Contract: rules_violated is a list with the rule id",
                     inc.get("rules_violated", [""])[0].startswith("RULE_PPE_01: ")))
results.append(check("Contract: detected_entities lists the classes involved",
                     inc.get("metadata", {}).get("detected_entities") == ["Person"]))
results.append(check("Contract: payload is JSON-serialisable", bool(json.dumps(inc))))
results.append(check("Contract: snapshot/clip paths are named after the event",
                     inc.get("snapshot_url") == f"/media/snapshots/{inc.get('event_id')}.jpg"
                     and inc.get("clip_url") == f"/media/clips/{inc.get('event_id')}.mp4"))

# --- zones ---
f = run([[person_at(50, 420)]], rules=["RULE_ZONE_01"])
results.append(check("Zone entry: fires immediately inside excavation edge", len(f) == 1))
results.append(check("Zone entry: location is the zone name", f and f[0][1]["location"] == "Excavation Edge"))
f = run([[person_at(500, 150)]] * 5, rules=["RULE_ZONE_01"])
results.append(check("Zone entry: person outside the zone doesn't fire", not f))
f = run([[person_at(50, 420)]] * 4, camera="cam_02", rules=["RULE_ZONE_01"])
results.append(check("Zone entry: zone on another camera is ignored", not f))

f = run([[WORKER]] * 70, rules=["RULE_ZONE_02"])  # 35 s
results.append(check("Loitering: fires after 30 s in crane swing area", len(f) == 1 and f[0][0] == 60,
                     f"{[i for i, _ in f]}"))

three = [person_at(430 + i * 50, 450) for i in range(3)]
four = three + [person_at(580, 450)]
results.append(check("Capacity: 3 workers on scaffold is allowed", not run([three] * 20, rules=["RULE_ZONE_03"])))
f = run([four] * 20, rules=["RULE_ZONE_03"])
results.append(check("Capacity: 4 workers for 5 s fires", len(f) == 1 and f[0][0] == 10))

# --- proximity ---
machine_near = {"class_name": "machinery", "confidence": 0.9, "bbox": [420, 150, 620, 400]}   # 20 px gap
machine_far = {"class_name": "machinery", "confidence": 0.9, "bbox": [560, 150, 640, 400]}    # 160 px gap
f = run([[WORKER, machine_near]] * 4, rules=["RULE_PROX_01"])
results.append(check("Proximity: worker next to machinery fires after 1 s", len(f) == 1 and f[0][0] == 2))
results.append(check("Proximity: severity CRITICAL", f and f[0][1]["severity"] == "CRITICAL"))
results.append(check("Proximity: far machinery doesn't fire",
                     not run([[WORKER, machine_far]] * 6, rules=["RULE_PROX_01"])))

# --- cooldown / disabled ---
f = run([[WORKER, machine_near]] * 50, rules=["RULE_PROX_01"])  # 25 s continuous
results.append(check("Cooldown: continuous violation re-fires every 10 s, not every frame",
                     [i for i, _ in f] == [2, 22, 42], f"{[i for i, _ in f]}"))
bottle = {"class_name": "bottle", "confidence": 0.9, "bbox": [50, 380, 70, 420]}
results.append(check("Disabled rule (food) never fires", not run([[bottle]] * 20, rules=["RULE_FOOD_01"])))

# --- presence (smoking) ---
SMOKER = {"class_name": "smoking", "confidence": 0.8, "bbox": [280, 100, 420, 240]}   # head and upper body
f = run([[WORKER, SMOKER]] * 8, rules=["RULE_SMOKE_01"])
results.append(check("Smoking: seen for 2 s fires", len(f) == 1 and f[0][0] == 4
                     and f[0][1]["event_type"] == "SMOKING", f"{[i for i, _ in f]}"))
results.append(check("Smoking: nobody smoking, no incident", not run([[WORKER]] * 8, rules=["RULE_SMOKE_01"])))
results.append(check("Vaping: not available yet, never fires",
                     not run([[{**SMOKER, "class_name": "vape"}]] * 8, rules=["RULE_SMOKE_02"])))
lying = {**WORKER, "bbox": [200, 350, 400, 400]}
results.append(check("Planned rules (pose) are skipped", not run([[lying]] * 700, rules=["RULE_POSE_01", "RULE_POSE_02"])))

# --- console settings ---
bad = [WORKER, NO_HARDHAT, VEST]
off = {"RULE_PPE_01": {"enabled": False}}
results.append(check("Settings: rule switched off never fires", not run([bad] * 20, rules=["RULE_PPE_01"], settings=off)))
f = run([bad] * 20, rules=["RULE_PPE_01", "RULE_ZONE_02"], settings={"RULE_ZONE_02": {"enabled": False}})
results.append(check("Settings: other rules keep working", len(f) == 1 and f[0][1]["metadata"]["rule_id"] == "RULE_PPE_01"))
# off for frames 0-4 (2.5 s of violation), back on at frame 5: the timer starts again from frame 5
f = run([bad] * 20, rules=["RULE_PPE_01"], settings=lambda i: off if i < 5 else {})
results.append(check("Settings: back on, the duration counts from when it was switched on",
                     len(f) == 1 and f[0][0] == 11, f"{[i for i, _ in f]}"))
f = run([bad] * 20, rules=["RULE_PPE_01"], settings={"RULE_PPE_01": {"min_duration_s": 6, "severity": "CRITICAL"}})
results.append(check("Settings: changed duration and severity are used",
                     len(f) == 1 and f[0][0] == 12 and f[0][1]["severity"] == "CRITICAL", f"{[i for i, _ in f]}"))
f = run([[person_at(430 + i * 50, 450) for i in range(3)]] * 20, rules=["RULE_ZONE_03"],
        settings={"RULE_ZONE_03": {"max_count": 2}})
results.append(check("Settings: lower max_count makes 3 workers over capacity", len(f) == 1))
f = run([bad] * 60, rules=["RULE_PPE_01"], settings={"RULE_PPE_01": {"cooldown_s": 20}})
results.append(check("Settings: longer cooldown", [i for i, _ in f] == [6, 46], f"{[i for i, _ in f]}"))

# active hours, in site time (Cairo is UTC+3 on 2026-10-07)
day_shift = {"RULE_PPE_01": {"active_hours": {"start": "07:00", "end": "19:00", "days": [0, 1, 2, 3, 4]}}}
wed_noon_cairo = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
wed_night_cairo = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)   # 21:00 in Cairo
sat_noon_cairo = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
hours = lambda start: run([bad] * 10, rules=["RULE_PPE_01"], settings=day_shift, start=start, site_tz="Africa/Cairo")
results.append(check("Hours: fires inside working hours", len(hours(wed_noon_cairo)) == 1))
results.append(check("Hours: quiet after hours (site time, not UTC)", not hours(wed_night_cairo)))
results.append(check("Hours: quiet on a day that isn't listed", not hours(sat_noon_cairo)))
night = {"RULE_PPE_01": {"active_hours": {"start": "22:00", "end": "06:00", "days": [2]}}}   # Wednesday night shift
thu_2am_cairo = datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc)
results.append(check("Hours: night shift past midnight counts for the day it started",
                     len(run([bad] * 10, rules=["RULE_PPE_01"], settings=night, start=thu_2am_cairo,
                             site_tz="Africa/Cairo")) == 1))

# --- zones redrawn in the console (fractions of the picture, scaled with the detection's frame_size) ---
def run_zones(objects, zones, frame_size=(640, 480)):
    engine = RuleEngine({PLUGIN["plugin_id"]: dict(PLUGIN, rules=[r for r in PLUGIN["rules"] if r["rule_id"] == "RULE_ZONE_01"])})
    engine.zones[PLUGIN["plugin_id"]] = zones
    event = {"timestamp": T0.isoformat(), "camera_id": "cam_01", "frame_id": 0, "plugin_id": PLUGIN["plugin_id"],
             "detections": objects, "frame_size": list(frame_size) if frame_size else None}
    return engine.process(event)

top_right = {"excavation_edge": [[0.75, 0.0], [1.0, 0.0], [1.0, 0.4], [0.75, 0.4]]}   # 480-640 x, 0-192 y at 640x480
results.append(check("Redrawn zone: a person inside the new area fires", len(run_zones([person_at(540, 150)], top_right)) == 1))
results.append(check("Redrawn zone: the old area no longer fires", not run_zones([person_at(50, 420)], top_right)))
results.append(check("Redrawn zone: scales to the camera's resolution",
                     len(run_zones([person_at(1620, 400)], top_right, frame_size=(1920, 1080))) == 1))
results.append(check("Redrawn zone: without a frame size the plugin's polygon is used",
                     len(run_zones([person_at(50, 420)], top_right, frame_size=None)) == 1))

# --- plugin errors ---
for name, broken in [("unknown rule type", {**PLUGIN, "rules": [{"rule_id": "X", "type": "magic"}]}),
                     ("unknown zone", {**PLUGIN, "rules": [{**PLUGIN["rules"][1], "zone": "nowhere"}]})]:
    try:
        RuleEngine({"p": broken})
        results.append(check(f"Plugin error: {name} is rejected", False))
    except ValueError:
        results.append(check(f"Plugin error: {name} is rejected", True))

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
