import os
import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "./plugins")
DETECTION_STREAM = "detections"
INCIDENT_STREAM = "incidents"
CONSUMER_GROUP = "event_engine"
CONSUMER_NAME = "engine_01"
COOLDOWN_SECONDS = float(os.getenv("RULE_COOLDOWN_SECONDS", "10"))

# tracks last fire time per (camera_id, rule_id)
_last_fired: dict[tuple, float] = {}


def load_plugins(plugins_dir: str) -> dict:
    plugins = {}
    for path in Path(plugins_dir).glob("*.json"):
        with open(path) as f:
            plugin = json.load(f)
            plugins[plugin["plugin_id"]] = plugin
    print(f"[EE] Loaded plugins: {list(plugins.keys())}", flush=True)
    return plugins


def apply_rules(event: dict, plugins: dict) -> list[dict]:
    plugin_id = event.get("plugin_id")
    plugin = plugins.get(plugin_id)
    if not plugin:
        return []

    objects = json.loads(event.get("objects", "[]"))
    incidents = []

    for rule in plugin.get("rules", []):
        trigger_classes = set(rule.get("trigger_classes", []))
        matching = [o for o in objects if o["class"] in trigger_classes]
        if not matching:
            continue

        cooldown_key = (event.get("camera_id", ""), rule["rule_id"])
        now = time.monotonic()
        if now - _last_fired.get(cooldown_key, 0) < COOLDOWN_SECONDS:
            continue
        _last_fired[cooldown_key] = now

        incidents.append({
            "incident_id": str(uuid.uuid4()),
            "timestamp_start": event.get("timestamp", ""),
            "timestamp_end": datetime.now(timezone.utc).isoformat(),
            "camera_id": event.get("camera_id", ""),
            "plugin_id": plugin_id,
            "rule_id": rule["rule_id"],
            "event_type": rule["event_type"],
            "severity": rule["severity"],
            "zone_id": rule.get("zone_id", ""),
            "objects_involved": json.dumps(matching),
            "rule_triggered": rule["rule_id"],
            "source": "laptop_simulation",
            "model": event.get("model", ""),
        })

    return incidents


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    plugins = load_plugins(PLUGINS_DIR)

    try:
        r.xgroup_create(DETECTION_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print(f"[EE] Listening on '{DETECTION_STREAM}'...", flush=True)

    while True:
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
                incidents = apply_rules(data, plugins)
                for incident in incidents:
                    r.xadd(INCIDENT_STREAM, incident, maxlen=1000)
                    print(f"[EE] Incident: {incident['event_type']}  severity={incident['severity']}", flush=True)
                r.xack(DETECTION_STREAM, CONSUMER_GROUP, event_id)


if __name__ == "__main__":
    main()
