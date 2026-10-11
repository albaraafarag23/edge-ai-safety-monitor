"""The end-of-day summary email: what happened on site in the last 24 hours, in a few plain sentences, and what is
still waiting for someone. Sent once a day at DIGEST_TIME (site time, e.g. "18:00"); empty = off (the default).

The figures come from the backend (GET /internal/daily-summary, with the internal token). The day it was last
sent is kept in Redis, so a restart doesn't send it twice; a failed send is tried again every 15 minutes.
Same language (EMAIL_LANGUAGE), recipients and look as the alert email (email_template.py).
"""
import html
import os
import time
from datetime import datetime, time as clock
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import httpx

import email_template as et
import notify
from report import arabic_names

DIGEST_TIME = os.getenv("DIGEST_TIME", "").strip()
LAST_SENT_KEY = "ai_reporting:digest:last_date"
LAST_TRY_KEY = "ai_reporting:digest:last_try"
RETRY_S = 15 * 60

TYPE_EN = {
    "PPE_MISSING": "missing safety gear", "RESTRICTED_ZONE_ENTRY": "entering a restricted area",
    "LOITERING_HAZARD_ZONE": "staying in a danger zone", "ZONE_OVER_CAPACITY": "too many people in one area",
    "PERSON_NEAR_MACHINERY": "getting too close to machinery", "SMOKING": "smoking", "VAPING": "vaping",
    "FOOD_IN_RESTRICTED_ZONE": "food or drink in a restricted area", "PERSON_DOWN": "a person down",
    "SLEEPING_ON_SITE": "someone lying still on site",
}
TEXT = {
    "en": {
        "brand": "SiteSentry · End of day",
        "subject_quiet": "Today on site: a quiet day",
        "subject": lambda n, waiting: f"Today on site: {n} incident{'s' if n != 1 else ''}"
                                      + (f", {waiting} still open" if waiting else ", all handled"),
        "quiet": "No incidents in the last 24 hours.",
        "headline": lambda n, waiting: f"{n} incident{'s' if n != 1 else ''} today"
                                       + (f", {waiting} still waiting for someone." if waiting else ", all handled."),
        "common": lambda what, n, where: f"Most common: {what} ({n})" + (f", mostly at {where}" if where else "") + ".",
        "busiest": lambda hour: f"Busiest time: around {hour}.",
        "handled": lambda t: f"Half were picked up within {t}.",
        "still_open": "Still open",
        "more": lambda n: f"and {n} more",
        "open_console": "Open the console",
        "footer": "Sent automatically by SiteSentry at the end of each day.",
        "units": ("seconds", "minutes", "hours"),
    },
    "ar": {
        "brand": "SiteSentry · نهاية اليوم",
        "subject_quiet": "الموقع اليوم: يوم هادئ",
        "subject": lambda n, waiting: f"الموقع اليوم: {_incidents_ar(n)}" + (f"، منها {waiting} مفتوحة" if waiting else "، عولجت كلها"),
        "quiet": "لا حوادث خلال آخر 24 ساعة.",
        "headline": lambda n, waiting: f"{_incidents_ar(n)} اليوم" + (f"، منها {waiting} بانتظار من يتولّاها." if waiting else "، عولجت كلها."),
        "common": lambda what, n, where: f"الأكثر شيوعًا: {what} ({n})" + (f"، وأغلبها في {where}" if where else "") + ".",
        "busiest": lambda hour: f"أكثر الأوقات ازدحامًا: نحو {hour}.",
        "handled": lambda t: f"نصف الحوادث تولّاها أحد خلال {t}.",
        "still_open": "ما زال مفتوحًا",
        "more": lambda n: f"و{n} أخرى",
        "open_console": "فتح لوحة التحكم",
        "footer": "أُرسلت تلقائيًا من SiteSentry في نهاية كل يوم.",
        "units": ("ثانية", "دقيقة", "ساعة"),
    },
}


def _incidents_ar(n: int) -> str:
    return et._count_ar(n, "حادثة واحدة", "حادثتان", "حوادث", "حادثة")


def due(now_local: datetime, last_sent: str | None, digest_time: str = DIGEST_TIME) -> bool:
    """True once the day's DIGEST_TIME has passed and today's summary hasn't been sent."""
    if not digest_time:
        return False
    hour, minute = (int(x) for x in digest_time.split(":"))
    return now_local.time() >= clock(hour, minute) and last_sent != now_local.date().isoformat()


def _hour(h: int, lang: str) -> str:
    if lang == "ar":
        return f"الساعة {h % 12 or 12} {'صباحًا' if h < 12 else 'مساءً'}"
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def _minutes(m: float, lang: str) -> str:
    if lang == "ar":  # counted nouns agree with the number in Arabic
        if m < 1:
            return et._count_ar(round(m * 60) or 1, "ثانية واحدة", "ثانيتين", "ثوانٍ", "ثانية")
        if m < 60:
            return et._count_ar(round(m), "دقيقة واحدة", "دقيقتين", "دقائق", "دقيقة")
        return f"{m / 60:.1f} ساعة"
    s, mins, hrs = TEXT[lang]["units"]
    if m < 1:
        return f"{round(m * 60)} {s}"
    if m < 60:
        return f"{round(m)} {mins}"
    return f"{m / 60:.1f} {hrs}"


def _type_name(key: str, lang: str, plugin: dict) -> str:
    if lang == "ar":
        return arabic_names({"event_type": key, "metadata": {}}, plugin).get("event_type") or key
    return TYPE_EN.get(key, key.replace("_", " ").lower())


def _place(location: str | None, lang: str, plugin: dict) -> str | None:
    if not location or location == "NOT SPECIFIED":
        return None
    if lang == "ar":
        # Arabic zone names are kept by zone id; the summary only has the English name
        zone_id = next((zid for zid, z in plugin.get("zones", {}).items() if z.get("name") == location), None)
        return arabic_names({"location": location, "metadata": {"zone_id": zone_id}}, plugin).get("location") or location
    return location


def sentences(summary: dict, lang: str, plugin: dict) -> list[str]:
    t = TEXT[lang]
    if not summary["total"]:
        return [t["quiet"]]
    lines = [t["headline"](summary["total"], summary["by_status"].get("open", 0))]
    if summary.get("top_type"):
        zone = summary.get("top_zone")
        lines.append(t["common"](_type_name(summary["top_type"]["key"], lang, plugin), summary["top_type"]["count"],
                                 _place(zone["key"], lang, plugin) if zone else None))
    if summary.get("busiest_hour") is not None:
        lines.append(t["busiest"](_hour(summary["busiest_hour"], lang)))
    if summary.get("median_minutes_to_handle") is not None:
        lines.append(t["handled"](_minutes(summary["median_minutes_to_handle"], lang)))
    return lines


def subject(summary: dict, lang: str) -> str:
    t = TEXT[lang]
    return t["subject"](summary["total"], summary["by_status"].get("open", 0)) if summary["total"] else t["subject_quiet"]


def _times(n: int, lang: str) -> str:
    if lang == "ar":
        return f"{n} مرات" if 3 <= n <= 10 else "مرتان" if n == 2 else f"{n} مرة"
    return f"{n} times"


def open_items(summary: dict, lang: str, plugin: dict) -> tuple[list[tuple[str, str, str]], int]:
    """(title, place and newest time, severity colour) for each group still open (the backend groups the same thing on
    the same camera and zone, with a count, most serious first); and how many open incidents those groups cover."""
    items, covered = [], 0
    for group in summary.get("open", []):
        n = group.get("count", 1)
        if lang == "ar":
            # Arabic zone names are kept by zone id; the group only has the English name
            zone_id = next((zid for zid, z in plugin.get("zones", {}).items() if z.get("name") == group.get("location")), None)
            group = {**group, "metadata": {**(group.get("metadata") or {}), "zone_id": zone_id}}
        names = arabic_names(group, plugin) if lang == "ar" else None
        title, _ = et.headline(group, lang, names)
        if n > 1:
            title += f" · {_times(n, lang)}"
        place = _place(group.get("location"), lang, plugin) or et.TEXT[lang]["camera"].format(id=group.get("camera_id"))
        items.append((title, f"{place} · {et.when({'timestamp': group.get('received_at')}, lang)}",
                      et.COLOR.get(group.get("severity"), et.MUTED)))
        covered += n
    return items, covered


def plain_text(summary: dict, lang: str, plugin: dict) -> str:
    t = TEXT[lang]
    lines = sentences(summary, lang, plugin)
    items, covered = open_items(summary, lang, plugin)
    if items:
        lines += ["", t["still_open"] + ":"] + [f"- {title} ({where})" for title, where, _ in items]
        extra = summary["open_total"] - covered
        if extra > 0:
            lines.append(f"- {t['more'](extra)}")
    if et.CONSOLE_URL:
        lines += ["", f"{t['open_console']}: {et.CONSOLE_URL}/app"]
    return "\n".join(lines + ["", t["footer"]])


def html_body(summary: dict, lang: str, plugin: dict) -> str:
    t = TEXT[lang]
    font = et.FONTS[lang]
    rtl = lang == "ar"
    esc = html.escape
    lh = (lambda en, ar: ar if rtl else en)  # noqa: E731  Arabic needs more line height
    lines = sentences(summary, lang, plugin)
    head, rest = lines[0], lines[1:]
    accent = et.COLOR["HIGH"] if summary["by_status"].get("open") else et.COLOR["LOW"]
    facts = "".join(f'<tr><td style="padding:0 28px 10px;font:16px/{lh(1.5, 1.7)} {font};color:{et.INK}">{esc(s)}</td></tr>'
                    for s in rest)
    items, covered = open_items(summary, lang, plugin)
    dot_pad = "4px 0 10px 10px" if rtl else "4px 10px 10px 0"
    rows = "".join(
        f'<tr><td valign="top" style="padding:{dot_pad};width:10px"><div style="width:8px;height:8px;border-radius:4px;'
        f'background:{color};margin-top:6px"></div></td><td style="padding:0 0 10px;font:15px/{lh(1.4, 1.6)} {font};color:{et.INK}">'
        f'<strong>{esc(title)}</strong><br><span style="color:{et.MUTED};font-size:13px">{esc(where)}</span></td></tr>'
        for title, where, color in items)
    extra = summary["open_total"] - covered
    more = (f'<tr><td></td><td style="font:13px/1.5 {font};color:{et.MUTED}">{esc(t["more"](extra))}</td></tr>') if extra > 0 else ""
    still = (f'<tr><td style="padding:14px 28px 6px;font:700 17px/1.4 {font};color:{et.INK}">{esc(t["still_open"])}</td></tr>'
             f'<tr><td style="padding:4px 28px 10px"><table role="presentation" cellpadding="0" cellspacing="0" width="100%">'
             f'{rows}{more}</table></td></tr>') if items else ""
    button = (f'<tr><td style="padding:10px 28px 26px"><a href="{esc(et.CONSOLE_URL)}/app" style="display:inline-block;'
              f'background:{et.INK};color:#ffffff;font:600 15px/1 {font};text-decoration:none;padding:14px 22px;border-radius:999px">'
              f'{esc(t["open_console"])}</a></td></tr>') if et.CONSOLE_URL else ""
    direction = 'dir="rtl" ' if rtl else ""
    html_attrs = ' lang="ar" dir="rtl"' if rtl else ""
    align = ";text-align:right" if rtl else ""
    return f"""<!doctype html>
<html{html_attrs}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body {direction}style="margin:0;padding:0;background:{et.PAGE}">
<div style="display:none;max-height:0;overflow:hidden">{esc(" ".join(lines))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{et.PAGE}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" {direction}width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden{align}">
  <tr><td style="height:6px;background:{accent};font-size:0;line-height:0">&nbsp;</td></tr>
  <tr><td style="padding:24px 28px 0;font:600 13px/1.4 {font};color:{et.MUTED}">{esc(t["brand"])}</td></tr>
  <tr><td style="padding:14px 28px 14px;font:700 26px/{lh(1.25, 1.5)} {font};color:{et.INK}">{esc(head)}</td></tr>
  {facts}
  {still}
  {button}
  <tr><td style="padding:8px 28px 26px;font:12px/1.5 {font};color:#9a958b">{esc(t["footer"])}</td></tr>
</table>
</td></tr></table>
</body></html>"""


def build(summary: dict, lang: str, plugin: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject(summary, lang)
    msg["From"] = notify.SMTP_FROM
    msg["To"] = ", ".join(notify.RECIPIENTS)
    if lang != "en":
        msg["Content-Language"] = lang
    msg.set_content(plain_text(summary, lang, plugin))
    msg.add_alternative(html_body(summary, lang, plugin), subtype="html")
    return msg


def maybe_send(r, backend_url: str, token: str, lang: str, plugin: dict):
    """Called from the main loop: sends today's summary once DIGEST_TIME has passed."""
    if not DIGEST_TIME or not notify.configured():
        return
    now = datetime.now(ZoneInfo(et.SITE_TIMEZONE))
    if not due(now, r.get(LAST_SENT_KEY)):
        return
    if time.time() - float(r.get(LAST_TRY_KEY) or 0) < RETRY_S:
        return
    r.set(LAST_TRY_KEY, time.time())
    try:
        res = httpx.get(f"{backend_url}/internal/daily-summary", params={"tz": et.SITE_TIMEZONE, "limit": 5}, timeout=10,
                        headers={"X-Internal-Token": token})
        res.raise_for_status()
        summary = res.json()
    except httpx.HTTPError as e:
        print(f"[AI] Daily summary: couldn't get the figures ({e}), will try again", flush=True)
        return
    error = notify.deliver(build(summary, lang, plugin))
    if error:
        print(f"[AI] Daily summary not sent ({error}), will try again in {RETRY_S // 60} min", flush=True)
        return
    r.set(LAST_SENT_KEY, now.date().isoformat())
    print(f"[AI] Daily summary sent to {', '.join(notify.RECIPIENTS)}: {subject(summary, lang)}", flush=True)
