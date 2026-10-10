"""For each incident: write an AI report, store it in the backend, email it to the supervisor.

Repeats of the same rule on the same camera within NOTIFY_COOLDOWN_S are recorded as
duplicates instead of generating another report and email.
Reports are written in each of REPORT_LANGUAGES (English always, Arabic by default too, at the same time);
the email goes out in EMAIL_LANGUAGE.
An email or report save that fails (network down, SMTP or backend unavailable) is retried from
outbox.py with growing waits; meanwhile the report shows the email as "retrying".
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx
import redis

import notify
import outbox
from report import (LANGUAGES, MODEL, approved_actions, arabic_names, generate_from_template,
                    generate_with_claude, missing_sections)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
# shared with the backend; POST /reports is only open to services that send it
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "../plugins")
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "../media"))
MEDIA_WAIT_S = float(os.getenv("MEDIA_WAIT_S", "12"))  # detector writes the clip ~3 s after the incident
NOTIFY_COOLDOWN_S = float(os.getenv("NOTIFY_COOLDOWN_S", "300"))
# English is always written (the report's `markdown`); "en" alone switches the Arabic version off
REPORT_LANGUAGES = ["en", *[lang for lang in os.getenv("REPORT_LANGUAGES", "en,ar").replace(" ", "").split(",")
                            if lang in LANGUAGES and lang != "en"]]
EMAIL_LANGUAGE = os.getenv("EMAIL_LANGUAGE", "en").strip().lower() or "en"
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


def media_path(url: str | None) -> Path | None:
    return MEDIA_DIR / url.removeprefix("/media/") if url and url.startswith("/media/") else None


def media_paths(incident: dict) -> tuple[Path | None, Path | None]:
    """The incident's snapshot and clip, or None for each that isn't on disk."""
    snapshot, clip = media_path(incident.get("snapshot_url")), media_path(incident.get("clip_url"))
    return (snapshot if snapshot and snapshot.exists() else None,
            clip if clip and clip.exists() else None)


def wait_for_media(incident: dict) -> tuple[Path | None, Path | None]:
    snapshot, clip = media_path(incident.get("snapshot_url")), media_path(incident.get("clip_url"))
    deadline = time.time() + MEDIA_WAIT_S
    while time.time() < deadline and not ((snapshot is None or snapshot.exists()) and (clip is None or clip.exists())):
        time.sleep(0.5)
    return media_paths(incident)


def save_report(event_id: str, markdown: str, generated_by: str, delivery: dict, tries: int = 3,
                markdown_ar: str | None = None) -> bool:
    body = {"event_id": event_id, "markdown": markdown, "markdown_ar": markdown_ar, "generated_by": generated_by,
            "delivery": delivery}
    for attempt in range(tries):  # the backend may not have stored the incident yet
        try:
            r = httpx.post(f"{BACKEND_URL}/reports", json=body, timeout=10,
                           headers={"X-Internal-Token": INTERNAL_API_TOKEN})
            if r.status_code != 404:
                r.raise_for_status()
                return True
        except httpx.HTTPError as e:
            print(f"[AI] Could not save report for {event_id}: {e}", flush=True)
        if attempt < tries - 1:
            time.sleep(2)
    return False


def store(r, event_id: str, markdown: str, generated_by: str, delivery: dict, tries: int = 3,
          markdown_ar: str | None = None):
    """Saves the report, or queues the save for later if the backend can't be reached."""
    if not save_report(event_id, markdown, generated_by, delivery, tries, markdown_ar):
        outbox.add(r, {"kind": "report", "event_id": event_id, "markdown": markdown, "markdown_ar": markdown_ar,
                       "generated_by": generated_by, "delivery": delivery})
        print(f"[AI] {event_id}: backend unavailable, report queued for retry", flush=True)


def retrying(delivery: dict, job: dict) -> dict:
    next_at = datetime.fromtimestamp(time.time() + outbox.next_wait(job["attempts"]), timezone.utc)
    return {**delivery, "status": "retrying", "attempts": job["attempts"],
            "next_attempt_at": next_at.isoformat(timespec="seconds")}


def email_content(job: dict) -> dict:
    """What a queued email says: {"lang", "markdown", "actions", "names"} (jobs queued before v2.4 are English)."""
    return job.get("email") or {"lang": "en", "markdown": job["markdown"], "actions": job.get("actions", [])}


def send_or_queue(r, incident: dict, markdown: str, generated_by: str, email: dict, job: dict | None = None,
                  markdown_ar: str | None = None) -> dict:
    """Sends the email (`email`: its language, report and actions); on failure queues it (again) and returns a
    "retrying" delivery record."""
    snapshot, clip = media_paths(incident)  # handle() has already waited for them
    delivery = notify.send(incident, email["markdown"], snapshot, clip, email["actions"], email["lang"],
                           email.get("names"))
    if job is not None:
        delivery["attempts"] = job["attempts"] + 1
    if delivery["status"] == "failed":
        job = outbox.add(r, {**(job or {}), "kind": "email", "event_id": incident["event_id"], "incident": incident,
                             "markdown": markdown, "markdown_ar": markdown_ar, "generated_by": generated_by,
                             "email": email})
        delivery = retrying(delivery, job)
    return delivery


def retry_job(r, job: dict):
    event_id = job["event_id"]
    if job["kind"] == "report":
        if outbox.expired(job):
            print(f"[AI] {event_id}: gave up saving the report after {job['attempts']} tries", flush=True)
        elif save_report(event_id, job["markdown"], job["generated_by"], job["delivery"], tries=1,
                         markdown_ar=job.get("markdown_ar")):
            print(f"[AI] {event_id}: queued report saved", flush=True)
        else:
            outbox.add(r, job)
        return

    if outbox.expired(job):
        delivery = {"status": "failed", "recipients": notify.RECIPIENTS, "attachments": [],
                    "attempts": job["attempts"],
                    "error": f"Gave up after {job['attempts']} tries over {outbox.RETRY_GIVE_UP_S / 3600:g} h"}
        print(f"[AI] {event_id}: gave up emailing after {job['attempts']} tries", flush=True)
    else:
        delivery = send_or_queue(r, job["incident"], job["markdown"], job["generated_by"], email_content(job), job,
                                 job.get("markdown_ar"))
        print(f"[AI] {event_id}: email retry {delivery['status']}", flush=True)
    store(r, event_id, job["markdown"], job["generated_by"], delivery, tries=1, markdown_ar=job.get("markdown_ar"))


def process_outbox(r):
    for job in outbox.take_due(r):
        try:
            retry_job(r, job)
        except Exception as e:  # keep the job rather than lose it
            print(f"[AI] {job.get('event_id')}: retry failed unexpectedly ({e}), will try again", flush=True)
            outbox.add(r, job)


def write_report(client, incident: dict, plugin: dict, actions: list[str], evidence: dict, lang: str) -> tuple[str, str]:
    """(markdown, generated_by) in one language: Claude, or the template if Claude is unavailable."""
    event_id = incident["event_id"]
    if client:
        try:
            markdown = generate_with_claude(client, incident, plugin, actions, evidence, lang)
            if not missing_sections(markdown, lang):
                return markdown, MODEL
            print(f"[AI] {event_id}: {lang} report missing sections {missing_sections(markdown, lang)}, "
                  f"using template", flush=True)
        except anthropic.AuthenticationError:
            print("[AI] Claude API key rejected, using the template", flush=True)
        except (anthropic.APIError, RuntimeError) as e:
            print(f"[AI] {event_id}: Claude unavailable for the {lang} report ({e}), using the template", flush=True)
    return generate_from_template(incident, actions, evidence, lang, plugin), "template"


def handle(r, incident: dict, plugins: dict, client, last_notified: dict):
    event_id = incident["event_id"]
    meta = incident.get("metadata") or {}
    key = (incident.get("camera_id"), meta.get("rule_id"))
    now = time.time()
    previous = last_notified.get(key)
    if previous and now - previous[0] < NOTIFY_COOLDOWN_S:
        ago = now - previous[0]
        store(r, event_id, f"Repeat of {previous[1]}: the supervisor was already notified "
                              f"{ago:.0f} s earlier for this rule on this camera.",
              "duplicate", {"status": "suppressed_duplicate", "duplicate_of": previous[1]},
              markdown_ar=(f"تكرار للحادثة {previous[1]}: سبق تنبيه المشرف قبل {ago:.0f} ثانية بشأن هذه القاعدة "
                           f"على هذه الكاميرا.") if "ar" in REPORT_LANGUAGES else None)
        print(f"[AI] {event_id}: repeat of {previous[1]}, not re-sent", flush=True)
        return
    last_notified[key] = (now, event_id)

    plugin = plugins.get(incident.get("plugin_id"), {})
    actions = {lang: approved_actions(plugin, meta.get("rule_id"), lang) for lang in REPORT_LANGUAGES}

    snapshot, clip = wait_for_media(incident)
    evidence = {"snapshot": snapshot is not None, "video_clip": clip is not None}

    # one request per language, at the same time
    with ThreadPoolExecutor(max_workers=len(REPORT_LANGUAGES)) as pool:
        futures = {lang: pool.submit(write_report, client, incident, plugin, actions[lang], evidence, lang)
                   for lang in REPORT_LANGUAGES}
        reports = {lang: f.result() for lang, f in futures.items()}
    markdown, generated_by = reports["en"]
    markdown_ar = reports["ar"][0] if "ar" in reports else None

    email_lang = EMAIL_LANGUAGE if EMAIL_LANGUAGE in reports else "en"
    email = {"lang": email_lang, "markdown": reports[email_lang][0], "actions": actions[email_lang],
             "names": arabic_names(incident, plugin) if email_lang == "ar" else None}
    delivery = send_or_queue(r, incident, markdown, generated_by, email, markdown_ar=markdown_ar)
    store(r, event_id, markdown, generated_by, delivery, markdown_ar=markdown_ar)
    languages = " + ".join(f"{lang} by {by}" for lang, (_, by) in reports.items())
    print(f"[AI] {event_id}: report {languages}, email ({email_lang}) {delivery['status']}"
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
    print(f"[AI] Ready. Plugins: {list(plugins)}. Reports by: {MODEL if client else 'template (no API key)'}, "
          f"in {', '.join(REPORT_LANGUAGES)}; email in {EMAIL_LANGUAGE}. "
          f"Email: {'to ' + ', '.join(notify.RECIPIENTS) if notify.configured() else 'not configured'}.", flush=True)

    if outbox.pending(r):
        print(f"[AI] {outbox.pending(r)} email(s)/report(s) waiting to be retried", flush=True)
    last_notified = {}
    while True:
        try:
            process_outbox(r)
        except Exception as e:  # a broken queued job must not stop new incidents
            print(f"[AI] Retry queue error: {e}", flush=True)
        messages = r.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {INCIDENT_STREAM: ">"}, count=5, block=2000)
        for _, entries in messages or []:
            for msg_id, data in entries:
                try:
                    handle(r, json.loads(data["data"]), plugins, client, last_notified)
                except (KeyError, json.JSONDecodeError):
                    print(f"[AI] Skipping message {msg_id}: not in the contract format", flush=True)
                except Exception as e:  # one bad incident must not stop reporting
                    print(f"[AI] Error handling message {msg_id}: {e}", flush=True)
                r.xack(INCIDENT_STREAM, CONSUMER_GROUP, msg_id)


if __name__ == "__main__":
    main()
