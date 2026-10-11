"""Emails an alert to the supervisor(s): a plain summary with the snapshot inline and what to do now, the full
report below it (email_template.py), and the snapshot and clip attached.

Configured through environment variables (see .env.example):
  SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  SMTP_TLS (starttls | ssl | none), SUPERVISOR_EMAILS (comma-separated), MAX_ATTACHMENT_MB,
  CONSOLE_URL (for the "Open this incident" button), SITE_TIMEZONE. The language (EMAIL_LANGUAGE) is chosen
  in main.py, which passes the report and actions in that language.
"""
import os
import smtplib
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
RECIPIENTS = [a.strip() for a in os.getenv("SUPERVISOR_EMAILS", "").split(",") if a.strip()]
MAX_ATTACHMENT_BYTES = float(os.getenv("MAX_ATTACHMENT_MB", "15")) * 1024 * 1024

def configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM and RECIPIENTS)


def build_email(incident: dict, report_md: str, snapshot: Path | None, clip: Path | None, actions: list[str] = (),
                lang: str = "en", names: dict | None = None):
    """Returns (message, list of attached file names). `names`: Arabic names for an Arabic email."""
    has_clip = bool(clip and clip.stat().st_size <= MAX_ATTACHMENT_BYTES)
    msg = EmailMessage()
    msg["Subject"] = email_template.subject(incident, lang, names)
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(RECIPIENTS)
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
         lang: str = "en", names: dict | None = None) -> dict:
    """Sends the report. Returns a delivery record that is stored with the report."""
    if not configured():
        return {"status": "not_configured", "recipients": [], "attachments": [],
                "error": "Set SMTP_HOST, SMTP_FROM/SMTP_USER and SUPERVISOR_EMAILS to send email"}
    msg, attached = build_email(incident, report_md, snapshot, clip, actions, lang, names)
    error = deliver(msg)
    return {"status": "failed" if error else "sent", "recipients": RECIPIENTS, "attachments": attached, "error": error}


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
