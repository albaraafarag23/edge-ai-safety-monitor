"""The alert email a supervisor reads: what happened in one plain sentence, where and when (site time),
the snapshot, and what to do now. The full formal report follows below a divider, for the record.

English or Arabic (EMAIL_LANGUAGE in main.py). The Arabic email is right-to-left and uses fonts every phone and
computer has, because email apps don't load web fonts. Arabic zone and item names come in `names`
(report.arabic_names).

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

COLOR = {"CRITICAL": "#c62828", "HIGH": "#e65100", "MEDIUM": "#b7791f", "LOW": "#2e7d32"}
# label, what the reader should do
SEVERITY = {
    "en": {
        "CRITICAL": ("Critical", "act now"),
        "HIGH": ("High", "act soon"),
        "MEDIUM": ("Medium", "check when you can"),
        "LOW": ("Low", "for your records"),
    },
    "ar": {
        "CRITICAL": ("حرجة", "تصرّف الآن"),
        "HIGH": ("مرتفعة", "تصرّف قريبًا"),
        "MEDIUM": ("متوسطة", "تحقّق عندما تستطيع"),
        "LOW": ("منخفضة", "للعلم والتسجيل"),
    },
}
TEXT = {
    "en": {
        "alert": "Alert", "brand": "SiteSentry · Site safety alert", "todo": "What to do now",
        "open": "Open this incident", "snapshot_alt": "Camera snapshot when the alert fired",
        "clip_note": "Snapshot when the alert fired. The video clip is attached to this email.",
        "clip_attached": "The video clip is attached.", "full_report": "Full report, for the safety record",
        "full_report_plain": "Full report", "footer": "Sent automatically by SiteSentry · Incident {id}",
        "camera": "Camera {id}", "unknown_time": "an unknown time",
    },
    "ar": {
        "alert": "تنبيه", "brand": "SiteSentry · تنبيه سلامة الموقع", "todo": "ما يجب فعله الآن",
        "open": "فتح هذه الحادثة", "snapshot_alt": "لقطة الكاميرا لحظة التنبيه",
        "clip_note": "لقطة لحظة التنبيه. مقطع الفيديو مرفق بهذه الرسالة.",
        "clip_attached": "مقطع الفيديو مرفق.", "full_report": "التقرير الكامل، لسجل السلامة",
        "full_report_plain": "التقرير الكامل", "footer": "أُرسلت تلقائيًا من SiteSentry · الحادثة {id}",
        "camera": "الكاميرا {id}", "unknown_time": "وقت غير معروف",
    },
}
WEEKDAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

INK, MUTED, LINE, PAGE = "#15130f", "#6b665c", "#e7e2d8", "#f4f1ea"
FONTS = {
    "en": "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif",
    "ar": "Tahoma,'Segoe UI','Geeza Pro','Noto Naskh Arabic',Arial,sans-serif",
}


def _items(meta: dict, lang: str, names: dict) -> str:
    """["hard_hat", "safety_vest"] -> "hard hat and safety vest" / "خوذة وسترة عاكسة"."""
    if lang == "ar":
        return " و".join(names.get("missing_equipment") or []) or "معدات الوقاية"
    found = [m.replace("_", " ") for m in meta.get("missing_equipment") or []]
    return " and ".join(found) or "safety equipment"


def _zone(incident: dict, lang: str = "en", names: dict | None = None) -> str | None:
    if lang == "ar" and names and names.get("location"):
        return names["location"]
    location = incident.get("location")
    return location if location and location != "NOT SPECIFIED" else None


def headline(incident: dict, lang: str = "en", names: dict | None = None) -> tuple[str, str]:
    """(short title for the subject line, one plain sentence for the email)."""
    names = names or {}
    meta = incident.get("metadata") or {}
    kind = incident.get("event_type")
    items = _items(meta, lang, names)
    if lang == "ar":
        zone = _zone(incident, lang, names) or "منطقة محظورة"
        plain = {
            "PPE_MISSING": (f"عامل بدون {items}", f"رُصد عامل بدون {items}."),
            "RESTRICTED_ZONE_ENTRY": (f"دخول إلى {zone}", f"دخل شخص إلى {zone}."),
            "LOITERING_HAZARD_ZONE": (f"شخص يبقى في {zone}", f"يبقى شخص في {zone} منذ فترة."),
            "ZONE_OVER_CAPACITY": (f"عدد زائد في {zone}", f"يوجد أشخاص أكثر من المسموح في {zone}."),
            "PERSON_NEAR_MACHINERY": ("عامل قريب جدًا من آلة", "اقترب عامل أكثر من اللازم من آلة تعمل."),
            "SMOKING": ("تدخين في الموقع", "رُصد شخص يدخّن في الموقع."),
            "VAPING": ("سيجارة إلكترونية في الموقع", "رُصد شخص يستخدم سيجارة إلكترونية في الموقع."),
            "FOOD_IN_RESTRICTED_ZONE": (f"طعام أو شراب في {zone}", f"تُرك طعام أو شراب في {zone}."),
            "PERSON_DOWN": ("سقوط شخص", "ربما سقط شخص أو أنه ممدد على الأرض."),
            "SLEEPING_ON_SITE": ("شخص ممدد بلا حركة", "يوجد شخص ممدد بلا حركة في الموقع منذ وقت طويل."),
        }
        event = names.get("event_type") or human(kind)
        return plain.get(kind, (event, f"رُصدت حادثة: {event}."))
    zone = _zone(incident) or "a restricted area"
    plain = {
        "PPE_MISSING": (f"Worker without a {items}", f"A worker was seen without a {items}."),
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


def when(incident: dict, lang: str = "en") -> str:
    """Site-time "Fri 9 Oct, 22:26" / "الجمعة 9 أكتوبر، 22:26"; the raw value if it can't be read."""
    raw = incident.get("timestamp") or ""
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(ZoneInfo(SITE_TIMEZONE))
    except (ValueError, KeyError):
        return raw or TEXT[lang]["unknown_time"]
    if lang == "ar":
        return f"{WEEKDAYS_AR[t.weekday()]} {t.day} {MONTHS_AR[t.month - 1]}، {t:%H:%M}"
    return f"{t:%a} {t.day} {t:%b}, {t:%H:%M}"


def _count_ar(n: int, one: str, two: str, few: str, many: str) -> str:
    """Arabic counted noun: 1 ثانية واحدة, 2 ثانيتين, 3-10 ثوانٍ, 11+ ثانية."""
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {few if 3 <= n % 100 <= 10 else many}"


def lasted(seconds, lang: str = "en") -> str | None:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    if lang == "ar":
        if seconds < 60:
            n = round(seconds)
            return f"استمرت {_count_ar(n, 'ثانية واحدة', 'ثانيتين', 'ثوانٍ', 'ثانية')}" if n else "استمرت أقل من ثانية"
        return f"استمرت {_count_ar(round(seconds / 60), 'دقيقة واحدة', 'دقيقتين', 'دقائق', 'دقيقة')}"
    if seconds < 60:
        n = round(seconds)
        return f"lasted {n} second{'' if n == 1 else 's'}" if n else "lasted under a second"
    minutes = round(seconds / 60)
    return f"lasted {minutes} minute{'' if minutes == 1 else 's'}"


def incident_link(incident: dict) -> str | None:
    return f"{CONSOLE_URL}/app/incidents/{incident.get('event_id')}" if CONSOLE_URL and incident.get("event_id") else None


def _severity(incident: dict, lang: str) -> tuple[str, str, str]:
    """(colour, label, urgency)."""
    label, urgency = SEVERITY[lang].get(incident.get("severity"), (TEXT[lang]["alert"], ""))
    return COLOR.get(incident.get("severity"), "#555555"), label, urgency


def subject(incident: dict, lang: str = "en", names: dict | None = None) -> str:
    _, label, _ = _severity(incident, lang)
    title, _ = headline(incident, lang, names)
    return f"{label}: {title} · {incident.get('camera_id', 'camera')}"


def facts(incident: dict, lang: str = "en", names: dict | None = None) -> list[str]:
    parts = [TEXT[lang]["camera"].format(id=incident.get("camera_id", "?")), _zone(incident, lang, names),
             when(incident, lang), lasted(incident.get("duration_seconds"), lang)]
    return [p for p in parts if p]


def plain_text(incident: dict, report_md: str, actions: list[str], has_clip: bool, lang: str = "en",
               names: dict | None = None) -> str:
    t = TEXT[lang]
    _, label, urgency = _severity(incident, lang)
    _, sentence = headline(incident, lang, names)
    lines = [f"{label.upper()} · {urgency}", "", sentence, " · ".join(facts(incident, lang, names)), ""]
    if actions:
        lines += [f"{t['todo']}:", *[f"  {i}. {a}" for i, a in enumerate(actions[:3], 1)], ""]
    if (link := incident_link(incident)):
        lines += [f"{t['open']}: {link}", ""]
    if has_clip:
        lines += [t["clip_attached"], ""]
    lines += ["-" * 40, t["full_report_plain"], "", report_md]
    return "\n".join(lines)


def html_body(incident: dict, report_md: str, actions: list[str], snapshot_cid: str | None, has_clip: bool,
              lang: str = "en", names: dict | None = None) -> str:
    t = TEXT[lang]
    font = FONTS[lang]
    rtl = lang == "ar"
    color, label, urgency = _severity(incident, lang)
    _, sentence = headline(incident, lang, names)
    esc = html.escape
    link = incident_link(incident)
    fact_line = " · ".join(facts(incident, lang, names))
    # Arabic: no capitals to transform, and letter-spacing breaks the joins between letters
    badge_caps = "" if rtl else "letter-spacing:.05em;text-transform:uppercase;"
    heading_caps = "" if rtl else ";text-transform:uppercase;letter-spacing:.04em"
    number_pad = "0 0 12px 12px" if rtl else "0 12px 12px 0"
    # Arabic needs more room between lines for the marks above and below the letters; English is unchanged
    lh = (lambda en, ar: ar if rtl else en)  # noqa: E731

    snapshot = (f'<tr><td style="padding:0 28px 8px"><img src="cid:{snapshot_cid}" width="544" alt="{esc(t["snapshot_alt"])}" '
                f'style="display:block;width:100%;max-width:544px;height:auto;border-radius:10px;border:0"></td></tr>') if snapshot_cid else ""
    clip_note = (f'<tr><td style="padding:0 28px 24px;font:13px/{lh(1.5, 1.7)} {font};color:{MUTED}">'
                 f'{esc(t["clip_note"])}</td></tr>') if has_clip else ""
    todo = ""
    if actions:
        items = "".join(
            f'<tr><td valign="top" style="padding:{number_pad};font:600 16px/{lh(1.5, 1.7)} {font};color:{color}">{i}.</td>'
            f'<td style="padding:0 0 12px;font:16px/{lh(1.5, 1.7)} {font};color:{INK}">{esc(a)}</td></tr>'
            for i, a in enumerate(actions[:3], 1))
        todo = (f'<tr><td style="padding:8px 28px 4px;font:700 18px/1.4 {font};color:{INK}">{esc(t["todo"])}</td></tr>'
                f'<tr><td style="padding:8px 28px 8px"><table role="presentation" cellpadding="0" cellspacing="0">{items}</table></td></tr>')
    button = (f'<tr><td style="padding:8px 28px 28px"><a href="{esc(link)}" style="display:inline-block;background:{INK};color:#ffffff;'
              f'font:600 15px/1 {font};text-decoration:none;padding:14px 22px;border-radius:999px">{esc(t["open"])}</a></td></tr>') if link else ""
    report_html = markdown.markdown(report_md)
    # the formal report keeps its content but reads as a quiet appendix
    report_html = (report_html.replace("<h1>", f'<p style="margin:0 0 8px;font:600 14px/1.4 {font};color:{MUTED}">')
                   .replace("</h1>", "</p>")
                   .replace("<h2>", f'<p style="margin:14px 0 4px;font:600 12px/1.4 {font};color:{MUTED}{heading_caps}">')
                   .replace("</h2>", "</p>"))
    direction = 'dir="rtl" ' if rtl else ""
    html_attrs = ' lang="ar" dir="rtl"' if rtl else ""
    align = ";text-align:right" if rtl else ""

    return f"""<!doctype html>
<html{html_attrs}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body {direction}style="margin:0;padding:0;background:{PAGE}">
<div style="display:none;max-height:0;overflow:hidden">{esc(sentence)} {esc(fact_line)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" {direction}width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden{align}">
  <tr><td style="height:6px;background:{color};font-size:0;line-height:0">&nbsp;</td></tr>
  <tr><td style="padding:24px 28px 0;font:600 13px/1.4 {font};color:{MUTED}">{esc(t["brand"])}</td></tr>
  <tr><td style="padding:14px 28px 0"><span style="display:inline-block;background:{color};color:#ffffff;font:700 12px/{lh(1, 1.3)} {font};
      {badge_caps}padding:7px 10px;border-radius:999px">{esc(label)} · {esc(urgency)}</span></td></tr>
  <tr><td style="padding:16px 28px 6px;font:700 26px/{lh(1.25, 1.5)} {font};color:{INK}">{esc(sentence)}</td></tr>
  <tr><td style="padding:0 28px 22px;font:15px/{lh(1.5, 1.7)} {font};color:{MUTED}">{esc(fact_line)}</td></tr>
  {snapshot}
  {clip_note}
  {todo}
  {button}
  <tr><td style="padding:0 28px"><div style="border-top:1px solid {LINE}"></div></td></tr>
  <tr><td style="padding:20px 28px 8px;font:13px/{lh(1.6, 1.8)} {font};color:{MUTED}">
    <p style="margin:0 0 6px;font:600 13px/1.4 {font};color:{INK}">{esc(t["full_report"])}</p>
    {report_html}
  </td></tr>
  <tr><td style="padding:16px 28px 26px;font:12px/1.5 {font};color:#9a958b">{esc(t["footer"].format(id=incident.get("event_id", "")))}</td></tr>
</table>
</td></tr></table>
</body></html>"""
