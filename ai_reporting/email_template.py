"""The alert email a supervisor reads: what happened in one plain sentence, where and when (site time),
the snapshot, and what to do now. The full formal report follows below a divider, for the record.

Email clients ignore most CSS, so the HTML is a single table-based column with inline styles.
"""
import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import markdown

from report import human

SITE_TIMEZONE = os.getenv("SITE_TIMEZONE", "Africa/Cairo")
# public address of the console, for the "Open this incident" button (no button when empty)
CONSOLE_URL = os.getenv("CONSOLE_URL", "").rstrip("/")

# colour, label, what the reader should do
SEVERITY = {
    "CRITICAL": ("#c62828", "Critical", "act now"),
    "HIGH": ("#e65100", "High", "act soon"),
    "MEDIUM": ("#b7791f", "Medium", "check when you can"),
    "LOW": ("#2e7d32", "Low", "for your records"),
}

INK, MUTED, LINE, PAGE = "#15130f", "#6b665c", "#e7e2d8", "#f4f1ea"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _items(meta: dict) -> str:
    """["hard_hat", "safety_vest"] -> "hard hat and safety vest"."""
    names = [m.replace("_", " ") for m in meta.get("missing_equipment") or []]
    return " and ".join(names) or "safety equipment"


def _zone(incident: dict) -> str | None:
    location = incident.get("location")
    return location if location and location != "NOT SPECIFIED" else None


def headline(incident: dict) -> tuple[str, str]:
    """(short title for the subject line, one plain sentence for the email)."""
    meta = incident.get("metadata") or {}
    zone = _zone(incident) or "a restricted area"
    kind = incident.get("event_type")
    plain = {
        "PPE_MISSING": (f"Worker without a {_items(meta)}", f"A worker was seen without a {_items(meta)}."),
        "RESTRICTED_ZONE_ENTRY": (f"Someone entered {zone}", f"Someone walked into {zone}."),
        "LOITERING_HAZARD_ZONE": (f"Someone staying in {zone}", f"Someone has been staying in {zone}."),
        "ZONE_OVER_CAPACITY": (f"Too many people in {zone}", f"There are too many people in {zone}."),
        "PERSON_NEAR_MACHINERY": ("Worker too close to machinery", "A worker got too close to working machinery."),
        "SMOKING": ("Smoking on site", "Someone was seen smoking on site."),
        "VAPING": ("Vaping on site", "Someone was seen vaping on site."),
        "FOOD_IN_RESTRICTED_ZONE": (f"Food or drink in {zone}", f"Food or drink was left in {zone}."),
        "PERSON_DOWN": ("Person down", "A person may have fallen or is lying on the ground."),
        "SLEEPING_ON_SITE": ("Someone lying still on site", "Someone has been lying still on site for a long time."),
    }
    return plain.get(kind, (human(kind), f"{human(kind)} was detected."))


def when(incident: dict) -> str:
    """Site-time "Fri 9 Oct, 22:26"; the raw value if it can't be read."""
    raw = incident.get("timestamp") or ""
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(ZoneInfo(SITE_TIMEZONE))
    except (ValueError, KeyError):
        return raw or "an unknown time"
    return f"{t:%a} {t.day} {t:%b}, {t:%H:%M}"


def lasted(seconds) -> str | None:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    if seconds < 60:
        n = round(seconds)
        return f"lasted {n} second{'' if n == 1 else 's'}" if n else "lasted under a second"
    minutes = round(seconds / 60)
    return f"lasted {minutes} minute{'' if minutes == 1 else 's'}"


def incident_link(incident: dict) -> str | None:
    return f"{CONSOLE_URL}/app/incidents/{incident.get('event_id')}" if CONSOLE_URL and incident.get("event_id") else None


def subject(incident: dict) -> str:
    _, label, _ = SEVERITY.get(incident.get("severity"), ("", "Alert", ""))
    title, _ = headline(incident)
    return f"{label}: {title} · {incident.get('camera_id', 'camera')}"


def facts(incident: dict) -> list[str]:
    parts = [f"Camera {incident.get('camera_id', '?')}", _zone(incident), when(incident), lasted(incident.get("duration_seconds"))]
    return [p for p in parts if p]


def plain_text(incident: dict, report_md: str, actions: list[str], has_clip: bool) -> str:
    _, label, urgency = SEVERITY.get(incident.get("severity"), ("", "Alert", ""))
    _, sentence = headline(incident)
    lines = [f"{label.upper()} · {urgency}", "", sentence, " · ".join(facts(incident)), ""]
    if actions:
        lines += ["What to do now:", *[f"  {i}. {a}" for i, a in enumerate(actions[:3], 1)], ""]
    if (link := incident_link(incident)):
        lines += [f"Open this incident: {link}", ""]
    if has_clip:
        lines += ["The video clip is attached.", ""]
    lines += ["-" * 40, "Full report", "", report_md]
    return "\n".join(lines)


def html_body(incident: dict, report_md: str, actions: list[str], snapshot_cid: str | None, has_clip: bool) -> str:
    color, label, urgency = SEVERITY.get(incident.get("severity"), ("#555555", "Alert", ""))
    _, sentence = headline(incident)
    esc = html.escape
    link = incident_link(incident)

    snapshot = (f'<tr><td style="padding:0 28px 8px"><img src="cid:{snapshot_cid}" width="544" alt="Camera snapshot when the alert fired" '
                f'style="display:block;width:100%;max-width:544px;height:auto;border-radius:10px;border:0"></td></tr>') if snapshot_cid else ""
    clip_note = (f'<tr><td style="padding:0 28px 24px;font:13px/1.5 {FONT};color:{MUTED}">'
                 f'Snapshot when the alert fired. The video clip is attached to this email.</td></tr>') if has_clip else ""
    todo = ""
    if actions:
        items = "".join(
            f'<tr><td valign="top" style="padding:0 12px 12px 0;font:600 16px/1.5 {FONT};color:{color}">{i}.</td>'
            f'<td style="padding:0 0 12px;font:16px/1.5 {FONT};color:{INK}">{esc(a)}</td></tr>'
            for i, a in enumerate(actions[:3], 1))
        todo = (f'<tr><td style="padding:8px 28px 4px;font:700 18px/1.4 {FONT};color:{INK}">What to do now</td></tr>'
                f'<tr><td style="padding:8px 28px 8px"><table role="presentation" cellpadding="0" cellspacing="0">{items}</table></td></tr>')
    button = (f'<tr><td style="padding:8px 28px 28px"><a href="{esc(link)}" style="display:inline-block;background:{INK};color:#ffffff;'
              f'font:600 15px/1 {FONT};text-decoration:none;padding:14px 22px;border-radius:999px">Open this incident</a></td></tr>') if link else ""
    report_html = markdown.markdown(report_md)
    # the formal report keeps its content but reads as a quiet appendix
    report_html = (report_html.replace("<h1>", f'<p style="margin:0 0 8px;font:600 14px/1.4 {FONT};color:{MUTED}">')
                   .replace("</h1>", "</p>")
                   .replace("<h2>", f'<p style="margin:14px 0 4px;font:600 12px/1.4 {FONT};color:{MUTED};text-transform:uppercase;letter-spacing:.04em">')
                   .replace("</h2>", "</p>"))

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{PAGE}">
<div style="display:none;max-height:0;overflow:hidden">{esc(sentence)} {esc(" · ".join(facts(incident)))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden">
  <tr><td style="height:6px;background:{color};font-size:0;line-height:0">&nbsp;</td></tr>
  <tr><td style="padding:24px 28px 0;font:600 13px/1.4 {FONT};color:{MUTED}">SiteSentry · Site safety alert</td></tr>
  <tr><td style="padding:14px 28px 0"><span style="display:inline-block;background:{color};color:#ffffff;font:700 12px/1 {FONT};
      letter-spacing:.05em;text-transform:uppercase;padding:7px 10px;border-radius:999px">{label} · {esc(urgency)}</span></td></tr>
  <tr><td style="padding:16px 28px 6px;font:700 26px/1.25 {FONT};color:{INK}">{esc(sentence)}</td></tr>
  <tr><td style="padding:0 28px 22px;font:15px/1.5 {FONT};color:{MUTED}">{esc(" · ".join(facts(incident)))}</td></tr>
  {snapshot}
  {clip_note}
  {todo}
  {button}
  <tr><td style="padding:0 28px"><div style="border-top:1px solid {LINE}"></div></td></tr>
  <tr><td style="padding:20px 28px 8px;font:13px/1.6 {FONT};color:{MUTED}">
    <p style="margin:0 0 6px;font:600 13px/1.4 {FONT};color:{INK}">Full report, for the safety record</p>
    {report_html}
  </td></tr>
  <tr><td style="padding:16px 28px 26px;font:12px/1.5 {FONT};color:#9a958b">Sent automatically by SiteSentry · Incident {esc(str(incident.get("event_id", "")))}</td></tr>
</table>
</td></tr></table>
</body></html>"""
