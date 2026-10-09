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
# rules switched off in the console: a Redis set per plugin, written by the backend (backend/rule_switches.py)
SWITCHED_OFF_KEY = "rules:off:{plugin_id}"
SWITCH_REFRESH_S = 2.0


def load_plugins(plugins_dir: str) -> dict:
    plugins = {}
    for path in Path(plugins_dir).glob("*.json"):
        with open(path) as f:
            plugin = json.load(f)
            plugins[plugin["plugin_id"]] = plugin
    print(f"[EE] Loaded plugins: {list(plugins.keys())}", flush=True)
    return plugins


def refresh_switches(r, engine: RuleEngine):
    for plugin_id in engine.plugins:
        off = r.smembers(SWITCHED_OFF_KEY.format(plugin_id=plugin_id))
        if off != engine.switched_off.get(plugin_id, set()):
            print(f"[EE] {plugin_id}: rules switched off: {sorted(off) or 'none'}", flush=True)
        engine.switched_off[plugin_id] = off


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    engine = RuleEngine(load_plugins(PLUGINS_DIR), cooldown_s=COOLDOWN_SECONDS)

    try:
        r.xgroup_create(DETECTION_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print(f"[EE] Listening on '{DETECTION_STREAM}'...", flush=True)

    last_refresh = 0.0
    while True:
        if time.monotonic() - last_refresh >= SWITCH_REFRESH_S:
            try:
                refresh_switches(r, engine)
            except redis.exceptions.RedisError as e:
                print(f"[EE] Couldn't read rule switches, keeping the last ones: {e}", flush=True)
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
