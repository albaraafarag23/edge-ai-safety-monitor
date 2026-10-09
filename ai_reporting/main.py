"""For each incident: write an AI report, store it in the backend, email it to the supervisor.

Repeats of the same rule on the same camera within NOTIFY_COOLDOWN_S are recorded as
duplicates instead of generating another report and email.
"""
import json
import os
import time
from pathlib import Path

import anthropic
import httpx
import redis

import notify
from report import MODEL, generate_from_template, generate_with_claude, missing_sections

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
# shared with the backend; POST /reports is only open to services that send it
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "../plugins")
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "../media"))
MEDIA_WAIT_S = float(os.getenv("MEDIA_WAIT_S", "12"))  # detector writes the clip ~3 s after the incident
NOTIFY_COOLDOWN_S = float(os.getenv("NOTIFY_COOLDOWN_S", "300"))
INCIDENT_STREAM = "incidents"
CONSUMER_GROUP = "ai_reporting"
CONSUMER_NAME = "reporter_01"


def load_plugins() -> dict:
    plugins = {}
    for path in Path(PLUGINS_DIR).glob("*.json"):
        plugin = json.loads(path.read_text())
        plugins[plugin["plugin_id"]] = plugin
    return plugins


def claude_client():
    """None if no credentials are configured; reports then use the template."""
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return None
    return anthropic.Anthropic()


def wait_for_media(incident: dict) -> tuple[Path | None, Path | None]:
    def path(url):
        return MEDIA_DIR / url.removeprefix("/media/") if url and url.startswith("/media/") else None

    snapshot, clip = path(incident.get("snapshot_url")), path(incident.get("clip_url"))
    deadline = time.time() + MEDIA_WAIT_S
    while time.time() < deadline and not ((snapshot is None or snapshot.exists()) and (clip is None or clip.exists())):
        time.sleep(0.5)
    return (snapshot if snapshot and snapshot.exists() else None,
            clip if clip and clip.exists() else None)


def save_report(event_id: str, markdown: str, generated_by: str, delivery: dict):
    body = {"event_id": event_id, "markdown": markdown, "generated_by": generated_by, "delivery": delivery}
    for attempt in range(3):  # the backend may not have stored the incident yet
        try:
            r = httpx.post(f"{BACKEND_URL}/reports", json=body, timeout=10,
                           headers={"X-Internal-Token": INTERNAL_API_TOKEN})
            if r.status_code != 404:
                r.raise_for_status()
                return
        except httpx.HTTPError as e:
            print(f"[AI] Could not save report for {event_id}: {e}", flush=True)
        time.sleep(2)
    print(f"[AI] Gave up saving report for {event_id}", flush=True)


def handle(incident: dict, plugins: dict, client, last_notified: dict):
    event_id = incident["event_id"]
    meta = incident.get("metadata") or {}
    key = (incident.get("camera_id"), meta.get("rule_id"))
    now = time.time()
    previous = last_notified.get(key)
    if previous and now - previous[0] < NOTIFY_COOLDOWN_S:
        save_report(event_id, f"Repeat of {previous[1]}: the supervisor was already notified "
                              f"{now - previous[0]:.0f} s earlier for this rule on this camera.",
                    "duplicate", {"status": "suppressed_duplicate", "duplicate_of": previous[1]})
        print(f"[AI] {event_id}: repeat of {previous[1]}, not re-sent", flush=True)
        return
    last_notified[key] = (now, event_id)

    plugin = plugins.get(incident.get("plugin_id"), {})
    rule = next((r for r in plugin.get("rules", []) if r.get("rule_id") == meta.get("rule_id")), {})
    actions = rule.get("recommended_actions", [])

    snapshot, clip = wait_for_media(incident)
    evidence = {"snapshot": snapshot is not None, "video_clip": clip is not None}

    markdown, generated_by = None, "template"
    if client:
        try:
            markdown = generate_with_claude(client, incident, plugin, actions, evidence)
            generated_by = MODEL
            if missing_sections(markdown):
                print(f"[AI] {event_id}: report missing sections {missing_sections(markdown)}, using template",
                      flush=True)
                markdown, generated_by = None, "template"
        except anthropic.AuthenticationError:
            print("[AI] Claude API key rejected, using the template", flush=True)
        except (anthropic.APIError, RuntimeError) as e:
            print(f"[AI] {event_id}: Claude unavailable ({e}), using the template", flush=True)
    if markdown is None:
        markdown = generate_from_template(incident, actions, evidence)

    delivery = notify.send(incident, markdown, snapshot, clip, actions)
    save_report(event_id, markdown, generated_by, delivery)
    print(f"[AI] {event_id}: report by {generated_by}, email {delivery['status']}"
          f"{' to ' + ', '.join(delivery['recipients']) if delivery['recipients'] else ''}"
          f"{' with ' + ', '.join(delivery['attachments']) if delivery['attachments'] else ''}"
          f"{' (' + delivery['error'] + ')' if delivery.get('error') else ''}", flush=True)


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.xgroup_create(INCIDENT_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    plugins = load_plugins()
    client = claude_client()
    print(f"[AI] Ready. Plugins: {list(plugins)}. Reports by: {MODEL if client else 'template (no API key)'}. "
          f"Email: {'to ' + ', '.join(notify.RECIPIENTS) if notify.configured() else 'not configured'}.", flush=True)

    last_notified = {}
    while True:
        messages = r.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {INCIDENT_STREAM: ">"}, count=5, block=2000)
        for _, entries in messages or []:
            for msg_id, data in entries:
                try:
                    handle(json.loads(data["data"]), plugins, client, last_notified)
                except (KeyError, json.JSONDecodeError):
                    print(f"[AI] Skipping message {msg_id}: not in the contract format", flush=True)
                except Exception as e:  # one bad incident must not stop reporting
                    print(f"[AI] Error handling message {msg_id}: {e}", flush=True)
                r.xack(INCIDENT_STREAM, CONSUMER_GROUP, msg_id)


if __name__ == "__main__":
    main()
