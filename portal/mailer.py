"""Plain emails from the portal (invites, sign-in alerts, approval requests). Its own sending account:
SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM. Not set: nothing is sent, the screen shows the
link instead and the server log says so."""
import asyncio
import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER


def configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def _send(to: list[str], subject: str, text: str):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"SiteSentry <{SMTP_FROM}>", SMTP_FROM
    msg["Bcc"] = ", ".join(to)
    msg.set_content(text)
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=20)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        if os.getenv("SMTP_TLS", "starttls") == "starttls":
            server.starttls(context=ssl.create_default_context())
    with server:
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


async def send(to: list[str] | str, subject: str, text: str) -> bool:
    """True if it went out. Never raises: a mail problem must not block a sign-in or an approval."""
    to = [to] if isinstance(to, str) else [a for a in to if a]
    if not to:
        return False
    if not configured():
        print(f"[Portal] Email not set up, not sent: {subject!r}", flush=True)
        return False
    try:
        await asyncio.get_running_loop().run_in_executor(None, _send, to, subject, text)
        return True
    except Exception as e:   # noqa: BLE001
        print(f"[Portal] Email failed ({type(e).__name__}): {subject!r}", flush=True)
        return False
