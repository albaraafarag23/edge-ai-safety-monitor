import os
import json
import time
from pathlib import Path

import redis

from rules import RuleEngine

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "./plugins")
DETECTION_STREAM = "detections"
INCIDENT_STREAM = "incidents"
MISSING_TTL_S = 3
CONSUMER_GROUP = "event_engine"
CONSUMER_NAME = "engine_01"
COOLDOWN_SECONDS = float(os.getenv("RULE_COOLDOWN_SECONDS", "10"))
# active_hours in rule settings are in this time zone
SITE_TIMEZONE = os.getenv("SITE_TIMEZONE", "Africa/Cairo")
# rule settings from the console: a Redis hash per plugin, rule_id -> JSON, written by the backend
# (backend/rule_settings.py)
SETTINGS_KEY = "rules:settings:{plugin_id}"
# zones drawn in the console: a Redis hash per plugin, "<camera_id>/<zone_id>" ->
# {"camera_id", "zone_id", "polygon": [[x, y], ...]} with the points as fractions of the picture (0-1)
ZONES_KEY = "zones:settings:{plugin_id}"
SETTINGS_REFRESH_S = 2.0
# wait between attempts while Redis is unreachable (doubles up to the maximum)
RECONNECT_MIN_S, RECONNECT_MAX_S = 1.0, 10.0


def load_plugins(plugins_dir: str) -> dict:
    plugins = {}
    for path in Path(plugins_dir).glob("*.json"):
        with open(path) as f:
            plugin = json.load(f)
            plugins[plugin["plugin_id"]] = plugin
    print(f"[EE] Loaded plugins: {list(plugins.keys())}", flush=True)
    return plugins


def refresh_settings(r, engine: RuleEngine):
    for plugin_id in engine.plugins:
        settings = {}
        for rule_id, raw in r.hgetall(SETTINGS_KEY.format(plugin_id=plugin_id)).items():
            try:
                settings[rule_id] = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[EE] Ignoring unreadable settings for {rule_id}", flush=True)
        if settings != engine.settings.get(plugin_id, {}):
            print(f"[EE] {plugin_id}: rule settings changed: {settings or 'none'}", flush=True)
        engine.settings[plugin_id] = settings
        zones = {}
        for field, raw in r.hgetall(ZONES_KEY.format(plugin_id=plugin_id)).items():
            try:
                drawing = json.loads(raw)
                # entries written before zones were per camera have no camera: they hold for every camera
                zones.setdefault(drawing.get("zone_id", field), {})[drawing.get("camera_id", "*")] = drawing["polygon"]
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                print(f"[EE] Ignoring unreadable zone {field}", flush=True)
        if zones != engine.zones.get(plugin_id, {}):
            print(f"[EE] {plugin_id}: zones redrawn in the console: {sorted(zones) or 'none'}", flush=True)
        engine.zones[plugin_id] = zones


def ensure_group(r):
    try:
        r.xgroup_create(DETECTION_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    engine = RuleEngine(load_plugins(PLUGINS_DIR), cooldown_s=COOLDOWN_SECONDS, site_tz=SITE_TIMEZONE)

    # A Redis restart must not restart the engine: that would lose the rule state (how long each
    # violation has lasted, cooldowns). redis-py reconnects on the next command, so wait and retry.
    wait = 0.0
    while True:
        try:
            # after a reconnect Redis may be back without the group (no append-only file)
            ensure_group(r)
            if wait:
                print("[EE] Redis is back", flush=True)
                wait = 0.0
            run(r, engine)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            wait = min(wait * 2, RECONNECT_MAX_S) if wait else RECONNECT_MIN_S
            print(f"[EE] Redis unreachable ({e}), retrying in {wait:.0f} s", flush=True)
            time.sleep(wait)
        except redis.exceptions.ResponseError as e:
            if "NOGROUP" not in str(e):
                raise
            print("[EE] Consumer group missing, creating it again", flush=True)


def run(r, engine: RuleEngine):
    print(f"[EE] Listening on '{DETECTION_STREAM}'...", flush=True)

    last_refresh = 0.0
    published = {}   # camera -> (what was last written to camera:<id>:missing, when)
    while True:
        if time.monotonic() - last_refresh >= SETTINGS_REFRESH_S:
            try:
                refresh_settings(r, engine)
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
                raise
            except redis.exceptions.RedisError as e:
                print(f"[EE] Couldn't read rule settings, keeping the last ones: {e}", flush=True)
            last_refresh = time.monotonic()

        messages = r.xreadgroup(
            CONSUMER_GROUP,
            CONSUMER_NAME,
            {DETECTION_STREAM: ">"},
            count=10,
            block=1000,
        )

        if not messages:
            continue

        for _, events in messages:
            for event_id, data in events:
                # each stream entry holds one detection message (docs/contracts.md) as JSON in "data"
                try:
                    detection = json.loads(data["data"])
                except (KeyError, json.JSONDecodeError):
                    print(f"[EE] Skipping message {event_id}: not in the contract format", flush=True)
                    r.xack(DETECTION_STREAM, CONSUMER_GROUP, event_id)
                    continue
                try:
                    incidents = engine.process(detection)
                except Exception as e:   # one malformed message must not restart the engine (and lose its timers)
                    print(f"[EE] Skipping message {event_id}: {type(e).__name__}: {e}", flush=True)
                    r.xack(DETECTION_STREAM, CONSUMER_GROUP, event_id)
                    continue
                publish_missing(r, engine, detection.get("camera_id", ""), published)
                for incident in incidents:
                    r.xadd(INCIDENT_STREAM, {"data": json.dumps(incident)}, maxlen=1000)
                    print(f"[EE] Incident {incident['event_id']}: {incident['camera_id']} {incident['event_type']}  "
                          f"severity={incident['severity']}  duration={incident['duration_seconds']}s", flush=True)
                r.xack(DETECTION_STREAM, CONSUMER_GROUP, event_id)


def publish_missing(r, engine, camera: str, published: dict):
    """camera:<id>:missing = {track_id: {"items": [...], "bbox": [...]}} for the detector's live picture
    (docs/contracts.md v2.9).
    Written when it changes and at least once a second; it expires after MISSING_TTL_S, so a stopped engine
    doesn't leave a stale label on anyone."""
    boxes = engine.missing_boxes.get(camera) or {}
    value = json.dumps({track: {"items": items, "bbox": boxes.get(track)}
                        for track, items in (engine.missing_now.get(camera) or {}).items()}, sort_keys=True)
    last = published.get(camera)
    now = time.monotonic()
    if last and last[0] == value and now - last[1] < 1.0:
        return
    published[camera] = (value, now)
    r.set(f"camera:{camera}:missing", value, ex=MISSING_TTL_S)


if __name__ == "__main__":
    main()
