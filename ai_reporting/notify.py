"""Emails a report to the supervisor(s), with the snapshot inline and the clip attached.

Configured through environment variables (see .env.example):
  SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  SMTP_TLS (starttls | ssl | none), SUPERVISOR_EMAILS (comma-separated), MAX_ATTACHMENT_MB.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

import markdown

from report import human

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
# docker-compose passes SMTP_TLS as "" when it isn't set, so an empty value means the default too
SMTP_TLS = (os.getenv("SMTP_TLS") or ("ssl" if SMTP_PORT == 465 else "starttls")).lower()
RECIPIENTS = [a.strip() for a in os.getenv("SUPERVISOR_EMAILS", "").split(",") if a.strip()]
MAX_ATTACHMENT_BYTES = float(os.getenv("MAX_ATTACHMENT_MB", "15")) * 1024 * 1024

SEVERITY_COLORS = {"CRITICAL": "#b00020", "HIGH": "#d35400", "MEDIUM": "#b7950b", "LOW": "#2e7d32"}


def configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM and RECIPIENTS)


def build_email(incident: dict, report_md: str, snapshot: Path | None, clip: Path | None):
    """Returns (message, list of attached file names)."""
    severity = incident.get("severity", "")
    msg = EmailMessage()
    location = incident.get("location")
    msg["Subject"] = (f"[{severity}] {human(incident.get('event_type'))} - camera {incident.get('camera_id', '?')}"
                      + (f" - {location}" if location and location != "NOT SPECIFIED" else ""))
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(RECIPIENTS)
    msg.set_content(report_md)  # plain-text version for clients that don't show HTML

    snapshot_cid = make_msgid(domain="safety-monitor")
    color = SEVERITY_COLORS.get(severity, "#555")
    image_html = (f'<p><img src="cid:{snapshot_cid[1:-1]}" alt="Incident snapshot" '
                  f'style="max-width:100%;border:1px solid #ccc"></p>') if snapshot else ""
    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:760px">
<div style="background:{color};color:#fff;padding:8px 12px;font-weight:bold">{severity} severity incident</div>
{markdown.markdown(report_md)}
{image_html}
<p style="color:#777;font-size:12px">Event {incident.get('event_id')} - generated automatically by the Edge AI Safety Monitor.</p>
</body></html>"""
    msg.add_alternative(html, subtype="html")

    attached = []
    if snapshot:
        data = snapshot.read_bytes()
        # inline in the HTML body, and also a normal attachment so it can be saved
        msg.get_payload()[1].add_related(data, "image", "jpeg", cid=snapshot_cid)
        msg.add_attachment(data, maintype="image", subtype="jpeg", filename=snapshot.name)
        attached.append(snapshot.name)
    if clip:
        if clip.stat().st_size <= MAX_ATTACHMENT_BYTES:
            msg.add_attachment(clip.read_bytes(), maintype="video", subtype="mp4", filename=clip.name)
            attached.append(clip.name)
    return msg, attached


def send(incident: dict, report_md: str, snapshot: Path | None, clip: Path | None) -> dict:
    """Sends the report. Returns a delivery record that is stored with the report."""
    if not configured():
        return {"status": "not_configured", "recipients": [], "attachments": [],
                "error": "Set SMTP_HOST, SMTP_FROM/SMTP_USER and SUPERVISOR_EMAILS to send email"}
    msg, attached = build_email(incident, report_md, snapshot, clip)
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
        return {"status": "failed", "recipients": RECIPIENTS, "attachments": attached, "error": str(e)}
    return {"status": "sent", "recipients": RECIPIENTS, "attachments": attached, "error": None}
