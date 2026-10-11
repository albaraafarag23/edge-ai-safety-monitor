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
CONSUMER_GROUP = "event_engine"
CONSUMER_NAME = "engine_01"
COOLDOWN_SECONDS = float(os.getenv("RULE_COOLDOWN_SECONDS", "10"))
# active_hours in rule settings are in this time zone
SITE_TIMEZONE = os.getenv("SITE_TIMEZONE", "Africa/Cairo")
# rule settings from the console: a Redis hash per plugin, rule_id -> JSON, written by the backend
# (backend/rule_settings.py)
SETTINGS_KEY = "rules:settings:{plugin_id}"
# zones redrawn in the console: a Redis hash per plugin, zone_id -> {"polygon": [[x, y], ...]} as fractions (0-1)
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
        for zone_id, raw in r.hgetall(ZONES_KEY.format(plugin_id=plugin_id)).items():
            try:
                zones[zone_id] = json.loads(raw)["polygon"]
            except (json.JSONDecodeError, KeyError, TypeError):
                print(f"[EE] Ignoring unreadable zone {zone_id}", flush=True)
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
                for incident in engine.process(detection):
                    r.xadd(INCIDENT_STREAM, {"data": json.dumps(incident)}, maxlen=1000)
                    print(f"[EE] Incident {incident['event_id']}: {incident['event_type']}  "
                          f"severity={incident['severity']}  duration={incident['duration_seconds']}s", flush=True)
                r.xack(DETECTION_STREAM, CONSUMER_GROUP, event_id)


if __name__ == "__main__":
    main()
