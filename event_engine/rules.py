"""Rule types for the event engine. Everything a rule checks comes from the plugin JSON.

Rule types:
  zone       - subjects inside a zone polygon (entry, loitering via min_duration_s,
               over capacity via max_count)
  proximity  - a subject too close to another class (person near machinery)
  ppe        - a person missing required equipment, optionally only inside a zone

Every rule can set min_duration_s: the condition must hold that long before an
incident fires. Short detector dropouts (under grace_s) don't reset the timer.

Rules can also be switched off at run time from the console (RuleEngine.switched_off), on top of
"enabled": false in the plugin, which means the rule isn't usable yet.
"""
import uuid
from datetime import datetime, timezone

DEFAULT_GRACE_S = 1.0
DEFAULT_COOLDOWN_S = 10.0


# ---------- geometry (boxes are [x1, y1, x2, y2] in pixels) ----------

def foot_point(box):
    """Bottom-centre of a box: where a person stands, used for zone checks."""
    return ((box[0] + box[2]) / 2, box[3])


def point_in_polygon(pt, polygon):
    x, y = pt
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def overlap_of(inner, outer):
    """Fraction of `inner`'s area that lies inside `outer`."""
    w = min(inner[2], outer[2]) - max(inner[0], outer[0])
    h = min(inner[3], outer[3]) - max(inner[1], outer[1])
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return 0.0 if w <= 0 or h <= 0 or area <= 0 else (w * h) / area


def box_gap(a, b):
    """Shortest distance between two boxes (0 if they touch or overlap)."""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return (dx * dx + dy * dy) ** 0.5


# ---------- per-frame checks: return the objects involved ([] = rule not active) ----------

def check_zone(rule, objects, zone):
    subjects = set(rule["subject_classes"])
    inside = [o for o in objects
              if o["class_name"] in subjects and point_in_polygon(foot_point(o["bbox"]), zone["polygon"])]
    max_count = rule.get("max_count")
    if max_count is not None:
        return inside if len(inside) > max_count else []
    return inside


def check_proximity(rule, objects, zone):
    subjects = [o for o in objects if o["class_name"] in set(rule["subject_classes"])]
    others = [o for o in objects if o["class_name"] in set(rule["near_classes"])]
    if zone:
        subjects = [o for o in subjects if point_in_polygon(foot_point(o["bbox"]), zone["polygon"])]
    involved = []
    for s in subjects:
        # distance limit scales with the subject's height in the image, so it works near and far
        limit = rule.get("max_gap_ratio", 0.5) * (s["bbox"][3] - s["bbox"][1])
        close = [o for o in others if box_gap(s["bbox"], o["bbox"]) <= limit]
        if close:
            involved.append(s)
            involved.extend(c for c in close if c not in involved)
    return involved


def check_ppe(rule, objects, zone):
    """Each required item can list present_classes (worn) and/or absent_classes (e.g. NO-Hardhat).
    An item counts as missing if an absent class overlaps the person, or if present_classes
    are given and none of them overlaps the person."""
    min_overlap = rule.get("min_overlap", 0.5)
    people = [o for o in objects if o["class_name"] in set(rule["subject_classes"])]
    if zone:
        people = [o for o in people if point_in_polygon(foot_point(o["bbox"]), zone["polygon"])]

    involved = []
    for p in people:
        missing = []
        for item in rule["required"]:
            def on_person(classes):
                return any(o["class_name"] in classes and overlap_of(o["bbox"], p["bbox"]) >= min_overlap
                           for o in objects)
            absent = item.get("absent_classes", [])
            present = item.get("present_classes", [])
            if (absent and on_person(absent)) or (present and not on_person(present)):
                missing.append(item["name"])
        if missing:
            involved.append({**p, "missing_equipment": missing})
    return involved


CHECKS = {"zone": check_zone, "proximity": check_proximity, "ppe": check_ppe}


def rule_classes(rule) -> set[str]:
    """Every class name a rule depends on (used to validate the plugin against the model)."""
    classes = set(rule.get("subject_classes", [])) | set(rule.get("near_classes", []))
    for item in rule.get("required", []):
        classes |= set(item.get("present_classes", [])) | set(item.get("absent_classes", []))
    return classes


# ---------- engine: per-frame checks + duration tracking + cooldown ----------

def _ts(value) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return datetime.now(timezone.utc).timestamp()


class RuleEngine:
    def __init__(self, plugins: dict, cooldown_s: float = DEFAULT_COOLDOWN_S):
        self.plugins = plugins
        self.cooldown_s = cooldown_s
        self._active = {}       # (camera, rule_id) -> {"start": ts, "last": ts}
        self._last_fired = {}   # (camera, rule_id) -> ts
        self.switched_off = {}  # plugin_id -> set of rule ids turned off in the console
        for plugin in plugins.values():
            for rule in plugin.get("rules", []):
                if rule.get("type") not in CHECKS:
                    raise ValueError(f"[{plugin['plugin_id']}] rule '{rule.get('rule_id')}' "
                                     f"has unknown type '{rule.get('type')}'")
                if rule.get("zone") and rule["zone"] not in plugin.get("zones", {}):
                    raise ValueError(f"[{plugin['plugin_id']}] rule '{rule['rule_id']}' "
                                     f"uses unknown zone '{rule['zone']}'")

    def process(self, event: dict) -> list[dict]:
        plugin = self.plugins.get(event.get("plugin_id"))
        if not plugin:
            return []
        objects = event.get("detections", [])
        camera = event.get("camera_id", "")
        now = _ts(event.get("timestamp"))

        incidents = []
        switched_off = self.switched_off.get(plugin["plugin_id"], set())
        for rule in plugin.get("rules", []):
            if not rule.get("enabled", True):
                continue
            if rule["rule_id"] in switched_off:
                # forget any running timer, so switching the rule back on starts from zero
                self._active.pop((camera, rule["rule_id"]), None)
                continue
            zone = plugin.get("zones", {}).get(rule.get("zone")) if rule.get("zone") else None
            if zone and zone.get("camera_id") not in (None, camera):
                continue

            involved = CHECKS[rule["type"]](rule, objects, zone)
            duration = self._track((camera, rule["rule_id"]), bool(involved), now,
                                   rule.get("grace_s", DEFAULT_GRACE_S))
            if duration is None or duration < rule.get("min_duration_s", 0):
                continue

            key = (camera, rule["rule_id"])
            if now - self._last_fired.get(key, float("-inf")) < rule.get("cooldown_s", self.cooldown_s):
                continue
            self._last_fired[key] = now
            incidents.append(self._incident(plugin, rule, zone, event, involved, duration))
        return incidents

    def _track(self, key, active, now, grace_s):
        """Returns how long the condition has held, or None if it isn't active."""
        state = self._active.get(key)
        if not active:
            if state and now - state["last"] > grace_s:
                del self._active[key]
            return None
        if state is None or now - state["last"] > grace_s:
            state = {"start": now}
            self._active[key] = state
        state["last"] = now
        return now - state["start"]

    @staticmethod
    def _incident(plugin, rule, zone, event, involved, duration):
        """Incident payload, as defined in docs/contracts.md."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        return {
            "event_id": event_id,
            "timestamp": event.get("timestamp", ""),
            "plugin_id": plugin["plugin_id"],
            "camera_id": event.get("camera_id", ""),
            "severity": rule["severity"],
            "event_type": rule["event_type"],
            "location": zone["name"] if zone else "NOT SPECIFIED",
            "duration_seconds": round(duration, 1),
            "rules_violated": [f"{rule['rule_id']}: {rule.get('description', '')}"],
            # the detector saves these files when it sees the incident (docs/contracts.md)
            "snapshot_url": f"/media/snapshots/{event_id}.jpg",
            "clip_url": f"/media/clips/{event_id}.mp4",
            "metadata": {
                "rule_id": rule["rule_id"],
                "zone_id": rule.get("zone"),
                "zone_name": zone["name"] if zone else None,
                "detected_entities": sorted({o["class_name"] for o in involved}),
                "missing_equipment": sorted({m for o in involved for m in o.get("missing_equipment", [])}),
                "objects_involved": involved,
                "frame_id": event.get("frame_id"),
                "model": event.get("model"),
            },
        }
