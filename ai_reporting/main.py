import os
import json

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
INCIDENT_STREAM = "incidents"
CONSUMER_GROUP = "ai_reporting"
CONSUMER_NAME = "reporter_01"


def generate_report(incident: dict) -> str:
    # TODO (Abdullah): replace stub with real LLM call.
    # Use ANTHROPIC_API_KEY with the Anthropic SDK, or OPENAI_API_KEY.
    # The incident dict has: incident_id, event_type, severity, zone_id,
    # camera_id, plugin_id, timestamp_start, objects_involved, rule_triggered.
    objects = json.loads(incident.get("objects_involved", "[]"))
    obj_summary = ", ".join(o["class"] for o in objects) or "unknown objects"

    return (
        f"Safety incident reported at {incident.get('timestamp_start', 'N/A')}. "
        f"Camera {incident.get('camera_id')} detected {obj_summary} "
        f"in zone '{incident.get('zone_id')}' triggering rule '{incident.get('rule_triggered')}'. "
        f"Severity: {incident.get('severity')}. "
        f"Immediate review recommended."
    )


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)

    try:
        r.xgroup_create(INCIDENT_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print("[AI] Reporting service ready, waiting for incidents...", flush=True)

    while True:
        messages = r.xreadgroup(
            CONSUMER_GROUP,
            CONSUMER_NAME,
            {INCIDENT_STREAM: ">"},
            count=5,
            block=2000,
        )

        if not messages:
            continue

        for _, events in messages:
            for event_id, data in events:
                report = generate_report(data)
                print(f"[AI] Report for {data.get('incident_id', '?')}:\n  {report}", flush=True)

                # TODO (Abdullah): POST report to backend once /reports endpoint exists
                # import httpx
                # httpx.post(f"{BACKEND_URL}/reports", json={
                #     "incident_id": data.get("incident_id"),
                #     "report_text": report,
                # })

                r.xack(INCIDENT_STREAM, CONSUMER_GROUP, event_id)


if __name__ == "__main__":
    main()
