"""Rule types for the event engine. Everything a rule checks comes from the plugin JSON.

Rule types:
  zone       - subjects inside a zone polygon (entry, loitering via min_duration_s,
               over capacity via max_count)
  proximity  - a subject too close to another class (person near machinery)
  ppe        - a person missing required equipment, optionally only inside a zone
  presence   - one of subject_classes is visible at all (e.g. a cigarette), optionally inside a zone

Every rule can set min_duration_s: the condition must hold that long before an
incident fires. Short detector dropouts (under grace_s) don't reset the timer.

"enabled": false or "planned": true in the plugin means the rule isn't usable yet (planned rules may
use a type that doesn't exist yet). On top of that, the console can switch rules off and change some of
their settings at run time (RuleEngine.settings, see RULE_SETTINGS below).
"""
import os
import uuid
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

DEFAULT_GRACE_S = 1.0
DEFAULT_COOLDOWN_S = 10.0
# a face match at least this strong counts someone in the per-person tally (cv_pipeline/faces.py FACE_STRONG)
SURE_FACE_SCORE = float(os.getenv("TALLY_MIN_FACE_SCORE", "0.50"))
# One long violation counts once in the tally: the same person breaking the same rule on the same camera is the
# same violation until they have kept the rule (or been out of sight) for this long. The incidents still repeat.
TALLY_GAP_S = float(os.getenv("TALLY_GAP_S", "300"))
# rule fields the console may change (backend/rule_settings.py validates the values)
RULE_SETTINGS = {"min_duration_s", "severity", "cooldown_s", "max_count", "active_hours"}


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


def check_presence(rule, objects, zone):
    subjects = set(rule["subject_classes"])
    found = [o for o in objects if o["class_name"] in subjects]
    if zone:
        found = [o for o in found if point_in_polygon(foot_point(o["bbox"]), zone["polygon"])]
    return found


CHECKS = {"zone": check_zone, "proximity": check_proximity, "ppe": check_ppe, "presence": check_presence}


def usable(rule) -> bool:
    """False for rules the plugin marks as not usable yet ("enabled": false or "planned": true)."""
    return rule.get("enabled", True) and not rule.get("planned", False)


def in_active_hours(active_hours, when: datetime) -> bool:
    """active_hours = {"start": "07:00", "end": "19:00", "days": [0..6] (Monday = 0)}, in site time.
    end before start spans midnight (a night shift). No active_hours = always active."""
    if not active_hours:
        return True
    start = time.fromisoformat(active_hours["start"])
    end = time.fromisoformat(active_hours["end"])
    now = when.time()
    if start <= end:
        in_window, day = start <= now < end, when.weekday()
    else:  # after midnight belongs to the shift that started the day before
        in_window = now >= start or now < end
        day = when.weekday() if now >= start else (when.weekday() - 1) % 7
    return in_window and day in active_hours.get("days", range(7))


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


def _people(involved: list[dict]) -> list[dict]:
    people = {}
    for o in involved:
        who = o.get("attributes") or {}
        if who.get("person_id") and who.get("person_name"):
            people[who["person_id"]] = {k: who[k] for k in ("person_id", "person_name", "person_name_ar") if who.get(k)}
    return [people[k] for k in sorted(people)]


def _violators(rule: dict, involved: list[dict]) -> list[dict]:
    """The recognised people who themselves broke the rule, for the per-person tally (docs/contracts.md v2.8).

    Stricter than `people` (everyone recognised in the incident). Someone is counted only when all of this holds:
    the rule is one a single person breaks (not a capacity rule, where nobody in particular is at fault, and not
    a rule the plugin marks `"personal": false`, e.g. a person down); they are the rule's subject (the person
    without the hard hat, the one smoking, the one inside the zone), not something near it; and the face match
    was strong (face_score >= SURE_FACE_SCORE), not a name settled by two weaker looks."""
    if rule.get("max_count") is not None or rule.get("personal") is False:
        return []
    subjects = set(rule.get("subject_classes", []))
    sure = {}
    for o in involved:
        who = o.get("attributes") or {}
        if (o.get("class_name") in subjects and who.get("identity") == "known" and who.get("person_id")
                and who.get("person_name") and (who.get("face_score") or 0) >= SURE_FACE_SCORE):
            sure[who["person_id"]] = {k: who[k] for k in ("person_id", "person_name", "person_name_ar", "face_score")
                                      if who.get(k)}
    return [sure[k] for k in sorted(sure)]


class RuleEngine:
    def __init__(self, plugins: dict, cooldown_s: float = DEFAULT_COOLDOWN_S, site_tz: str = "UTC"):
        self.plugins = plugins
        self.cooldown_s = cooldown_s
        self.site_tz = ZoneInfo(site_tz)   # active_hours are in site time
        self._active = {}       # (camera, rule_id) -> {"start": ts, "last": ts}
        self._last_fired = {}   # (camera, rule_id) -> ts
        # camera -> {track_id: [missing items]} as of the last frame: who lacks which equipment right now, by the
        # same rules that raise incidents (zones, switches and working hours included), before any waiting time.
        # main.py publishes it, and the detector writes it on the person's box in the live picture.
        self.missing_now = {}
        # camera -> {track_id: that person's box}: the detector falls back on it when a person's track number has
        # just changed (it does when someone is very close to the camera), so the label doesn't flicker off
        self.missing_boxes = {}
        # (camera, rule_id, person_id) -> {"last": when they were last seen breaking it, "counted": bool}
        self._episodes = {}
        self.settings = {}      # plugin_id -> {rule_id: {"enabled": bool, <RULE_SETTINGS>...}} from the console
        # plugin_id -> {zone_id: {camera_id: [[x, y], ...]}}: zones drawn in the console for one camera, as
        # fractions of the picture (0-1), so they fit any camera resolution; turned into pixels with each
        # detection's frame_size. "*" as the camera means every camera the plugin puts the zone on.
        self.zones = {}
        for plugin in plugins.values():
            for rule in plugin.get("rules", []):
                if rule.get("planned"):
                    continue
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
        missing_now = self.missing_now[camera] = {}
        missing_boxes = self.missing_boxes[camera] = {}
        now = _ts(event.get("timestamp"))

        incidents = []
        settings = self.settings.get(plugin["plugin_id"], {})
        site_now = datetime.fromtimestamp(now, self.site_tz)
        for rule in plugin.get("rules", []):
            if not usable(rule):
                continue
            changes = settings.get(rule["rule_id"], {})
            rule = {**rule, **{k: v for k, v in changes.items() if k in RULE_SETTINGS}}
            if changes.get("enabled") is False or not in_active_hours(rule.get("active_hours"), site_now):
                # forget any running timer, so the rule starts from zero when it's active again
                self._active.pop((camera, rule["rule_id"]), None)
                continue
            zone = None
            if rule.get("zone"):
                zone = self._zone(plugin, rule["zone"], camera, event.get("frame_size"))
                if zone is None:   # this camera doesn't look at that zone
                    continue

            involved = CHECKS[rule["type"]](rule, objects, zone)
            for o in involved:
                track_id = (o.get("attributes") or {}).get("track_id")
                if track_id is not None and o.get("missing_equipment"):
                    items = missing_now.setdefault(str(track_id), [])
                    missing_boxes[str(track_id)] = o["bbox"]
                    items.extend(m for m in o["missing_equipment"] if m not in items)
            self._note_episodes(camera, rule, involved, now)
            duration = self._track((camera, rule["rule_id"]), bool(involved), now,
                                   rule.get("grace_s", DEFAULT_GRACE_S))
            if duration is None or duration < rule.get("min_duration_s", 0):
                continue

            key = (camera, rule["rule_id"])
            if now - self._last_fired.get(key, float("-inf")) < rule.get("cooldown_s", self.cooldown_s):
                continue
            self._last_fired[key] = now
            incident = self._incident(plugin, rule, zone, event, involved, duration)
            for v in incident["metadata"]["violators"]:
                episode = self._episodes.get((camera, rule["rule_id"], v["person_id"]))
                # the tally counts this violation only in the first incident of it (docs/contracts.md v2.10)
                v["counted"] = bool(episode) and not episode["counted"]
                if episode:
                    episode["counted"] = True
            incidents.append(incident)
        return incidents

    def _note_episodes(self, camera: str, rule: dict, involved: list[dict], now: float):
        """Follows each sure-of person's violation of this rule over time (see TALLY_GAP_S)."""
        for v in _violators(rule, involved):
            key = (camera, rule["rule_id"], v["person_id"])
            episode = self._episodes.get(key)
            if episode is None or now - episode["last"] > TALLY_GAP_S:
                self._episodes[key] = episode = {"counted": False}
            episode["last"] = now
        if len(self._episodes) > 5000:   # a long-running engine: forget violations that ended long ago
            self._episodes = {k: e for k, e in self._episodes.items() if now - e["last"] <= TALLY_GAP_S}

    def _zone(self, plugin: dict, zone_id: str, camera: str, frame_size) -> dict | None:
        """The zone as this camera sees it, or None if the zone isn't on this camera.

        A zone drawn in the console for this camera wins (when the frame size is known). Otherwise the plugin's
        polygon applies on the camera the plugin names (every camera if it names none)."""
        zone = plugin.get("zones", {}).get(zone_id)
        if not zone:
            return None
        drawn = self.zones.get(plugin["plugin_id"], {}).get(zone_id)
        if isinstance(drawn, dict):
            mine = zone.get("camera_id") in (None, camera)
            drawn = drawn.get(camera) or (drawn.get("*") if mine else None)
        if drawn and frame_size and len(frame_size) == 2:
            width, height = frame_size
            return {**zone, "polygon": [[x * width, y * height] for x, y in drawn]}
        return zone if zone.get("camera_id") in (None, camera) else None

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
                # who was involved, when face recognition knew them (docs/contracts.md v2.6)
                "people": _people(involved),
                # the ones counted against in the per-person tally: sure of who, and they broke the rule (v2.8)
                "violators": _violators(rule, involved),
                "objects_involved": involved,
                "frame_id": event.get("frame_id"),
                "model": event.get("model"),
            },
        }
