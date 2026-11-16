"""Emails an alert to the supervisor(s): a plain summary with the snapshot inline and what to do now, the full
report below it (email_template.py), and the snapshot and clip attached.

Configured through environment variables (see .env.example):
  SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  SMTP_TLS (starttls | ssl | none), SUPERVISOR_EMAILS (comma-separated), MAX_ATTACHMENT_MB,
  CONSOLE_URL (for the "Open this incident" button), SITE_TIMEZONE. The language (EMAIL_LANGUAGE) is chosen
  in main.py, which passes the report and actions in that language.
"""
import json
import os
import smtplib

import redis
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

import email_template

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
# docker-compose passes SMTP_TLS as "" when it isn't set, so an empty value means the default too
SMTP_TLS = (os.getenv("SMTP_TLS") or ("ssl" if SMTP_PORT == 465 else "starttls")).lower()
# A fixed extra list from .env, besides the people who chose alerts in the console (notify:recipients, written
# by backend/alert_settings.py). They get incidents from EMAIL_MIN_SEVERITY up (default High) and the summary.
RECIPIENTS = [a.strip() for a in os.getenv("SUPERVISOR_EMAILS", "").split(",") if a.strip()]
EMAIL_MIN_SEVERITY = (os.getenv("EMAIL_MIN_SEVERITY") or "HIGH").upper()
RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
RECIPIENTS_KEY = "notify:recipients"
MAX_ATTACHMENT_BYTES = float(os.getenv("MAX_ATTACHMENT_MB", "15")) * 1024 * 1024

def configured() -> bool:
    """A mail server is set up. (Who gets what is decided per message: recipients().)"""
    return bool(SMTP_HOST and SMTP_FROM)


def people(r) -> list[dict]:
    """[{"email", "level", "summary"}]: the console's choices plus the fixed .env list."""
    chosen = []
    try:
        raw = r.get(RECIPIENTS_KEY) if r is not None else None
        chosen = [p for p in json.loads(raw or "[]") if isinstance(p, dict) and p.get("email")]
    except (ValueError, TypeError, redis.exceptions.RedisError):
        pass
    fixed = [{"email": a, "level": EMAIL_MIN_SEVERITY, "summary": True} for a in RECIPIENTS]
    out, seen = [], set()
    for p in chosen + fixed:
        if p["email"].lower() not in seen:
            seen.add(p["email"].lower())
            out.append(p)
    return out


def recipients(r, severity: str | None = None, summary: bool = False) -> list[str]:
    """Who should get this: an incident of `severity`, or (summary=True) the end-of-day summary."""
    if summary:
        return [p["email"] for p in people(r) if p.get("summary")]
    rank = RANK.get((severity or "").upper(), 3)
    return [p["email"] for p in people(r) if p.get("level") in RANK and rank <= RANK[p["level"]]]


def build_email(incident: dict, report_md: str, snapshot: Path | None, clip: Path | None, actions: list[str] = (),
                lang: str = "en", names: dict | None = None, to: list[str] | None = None):
    """Returns (message, list of attached file names). `names`: Arabic names for an Arabic email."""
    has_clip = bool(clip and clip.stat().st_size <= MAX_ATTACHMENT_BYTES)
    msg = EmailMessage()
    msg["Subject"] = email_template.subject(incident, lang, names)
    msg["From"] = SMTP_FROM
    # each person on Bcc: recipients don't see each other's addresses
    msg["To"] = SMTP_FROM
    msg["Bcc"] = ", ".join(to if to is not None else RECIPIENTS)
    # plain-text version for clients that don't show HTML
    msg.set_content(email_template.plain_text(incident, report_md, list(actions), has_clip, lang, names))
    if lang != "en":
        msg["Content-Language"] = lang

    snapshot_cid = make_msgid(domain="sitesentry")
    msg.add_alternative(email_template.html_body(incident, report_md, list(actions), snapshot_cid[1:-1] if snapshot else None,
                                                 has_clip, lang, names), subtype="html")

    attached = []
    if snapshot:
        data = snapshot.read_bytes()
        # inline in the HTML body, and also a normal attachment so it can be saved
        msg.get_payload()[1].add_related(data, "image", "jpeg", cid=snapshot_cid)
        msg.add_attachment(data, maintype="image", subtype="jpeg", filename=snapshot.name)
        attached.append(snapshot.name)
    if has_clip:
        msg.add_attachment(clip.read_bytes(), maintype="video", subtype="mp4", filename=clip.name)
        attached.append(clip.name)
    return msg, attached


def send(incident: dict, report_md: str, snapshot: Path | None, clip: Path | None, actions: list[str] = (),
         lang: str = "en", names: dict | None = None, r=None) -> dict:
    """Sends the report to everyone who asked for this severity. Returns a delivery record stored with the report."""
    if not configured():
        return {"status": "not_configured", "recipients": [], "attachments": [],
                "error": "Set SMTP_HOST and SMTP_FROM/SMTP_USER to send email"}
    to = recipients(r, incident.get("severity"))
    if not to:   # e.g. a Medium incident when everyone asked for High and Critical only
        return {"status": "not_needed", "recipients": [], "attachments": [], "error": None}
    msg, attached = build_email(incident, report_md, snapshot, clip, actions, lang, names, to)
    error = deliver(msg)
    return {"status": "failed" if error else "sent", "recipients": to, "attachments": attached, "error": error}


def deliver(msg: EmailMessage) -> str | None:
    """Sends one message through the SMTP server. None when sent, otherwise the error."""
    try:
        if SMTP_TLS == "ssl":
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            if SMTP_TLS == "starttls":
                server.starttls(context=ssl.create_default_context())
        with server:
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        return str(e)
    return None
