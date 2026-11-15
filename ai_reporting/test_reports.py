"""Checks for the report and email text in both languages, without Claude or an email server.

    cd ai_reporting && python test_reports.py      (needs: pip install markdown anthropic)
"""
import json
from pathlib import Path

import email_template
from report import (SECTIONS, approved_actions, arabic_names, generate_from_template, missing_sections,
                    rule_regulations, with_regulations)

PLUGIN = json.loads((Path(__file__).parent.parent / "plugins" / "construction_safety.json").read_text())
INCIDENT = {
    "event_id": "evt_test01", "timestamp": "2026-10-10T19:00:00.000Z", "plugin_id": "construction_safety",
    "camera_id": "cam_01", "severity": "HIGH", "event_type": "PPE_MISSING", "location": "Excavation Edge",
    "duration_seconds": 3.4, "rules_violated": ["RULE_PPE_01: Hard hat required on site"],
    "snapshot_url": None, "clip_url": None,
    "metadata": {"rule_id": "RULE_PPE_01", "zone_id": "excavation_edge", "zone_name": "Excavation Edge",
                 "detected_entities": ["Person", "NO-Hardhat"], "missing_equipment": ["hard_hat"]},
}
EVIDENCE = {"snapshot": True, "video_clip": False}
results = []


def check(name, ok):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")


en_actions = approved_actions(PLUGIN, "RULE_PPE_01", "en")
ar_actions = approved_actions(PLUGIN, "RULE_PPE_01", "ar")
check("Arabic approved actions come from the plugin's translations",
      len(ar_actions) == len(en_actions) == 3 and ar_actions[0].startswith("أوقف"))
check("A rule without a translation falls back to the English actions",
      approved_actions({"rules": PLUGIN["rules"]}, "RULE_PPE_01", "ar") == en_actions)

names = arabic_names(INCIDENT, PLUGIN)
check("Arabic names: event type, zone, items, detected classes",
      names["event_type"] == "معدات وقاية ناقصة" and names["location"] == "حافة الحفرة"
      and names["missing_equipment"] == ["خوذة"] and names["detected_entities"] == ["شخص", "بدون خوذة"])

en = generate_from_template(INCIDENT, en_actions, EVIDENCE, "en", PLUGIN)
ar = generate_from_template(INCIDENT, ar_actions, EVIDENCE, "ar", PLUGIN)
check("English template has every section", not missing_sections(en, "en"))
check("Arabic template has every Arabic section", not missing_sections(ar, "ar") and all(f"## {s}" in ar for s in SECTIONS["ar"]))
check("Arabic template uses the Arabic zone, rule description and actions",
      "حافة الحفرة" in ar and "RULE_PPE_01: ارتداء الخوذة إلزامي في الموقع" in ar and ar_actions[0] in ar)
check("Arabic template keeps IDs in Latin letters", "evt_test01" in ar and "cam_01" in ar)
check("Arabic template writes «غير محدد» for missing fields",
      "غير محدد" in generate_from_template({**INCIDENT, "camera_id": None}, ar_actions, EVIDENCE, "ar", PLUGIN))
check("An English report fails the Arabic section check", missing_sections(en, "ar") == SECTIONS["ar"])

subject = email_template.subject(INCIDENT, "ar", names)
html = email_template.html_body(INCIDENT, ar, ar_actions, "cid", False, "ar", names)
text = email_template.plain_text(INCIDENT, ar, ar_actions, False, "ar", names)
check("Arabic email subject", subject == "مرتفعة: عامل بدون خوذة · cam_01")
check("Arabic email is right-to-left with the plain sentence and actions",
      'dir="rtl"' in html and "رُصد عامل بدون خوذة." in html and "ما يجب فعله الآن" in html and ar_actions[0] in html)
check("Arabic email has no letter-spacing (it breaks Arabic letters)", "letter-spacing" not in html)
check("Arabic email shows site time with Arabic day and month", "السبت 10 أكتوبر، 22:00" in text)
check("Arabic durations", email_template.lasted(3.4, "ar") == "استمرت 3 ثوانٍ"
      and email_template.lasted(1, "ar") == "استمرت ثانية واحدة" and email_template.lasted(125, "ar") == "استمرت دقيقتين")
check("English email is unchanged in shape", email_template.subject(INCIDENT) == "High: Worker without a hard hat · cam_01"
      and 'dir="rtl"' not in email_template.html_body(INCIDENT, en, en_actions, "cid", False))

# ---------- end-of-day summary email ----------
import digest
from datetime import datetime

# who was involved (face recognition, contracts v2.6)
NAMED = {**INCIDENT, "metadata": {**INCIDENT["metadata"], "people": [
    {"person_id": "omar-ahmed", "person_name": "Omar Ahmed", "person_name_ar": "عمر أحمد"}]}}
check("Report names a recognised person, as something to confirm",
      "Omar Ahmed" in generate_from_template(NAMED, en_actions, EVIDENCE) and
      "People identified (automatic face recognition, to be confirmed): NOT SPECIFIED"
      in generate_from_template(INCIDENT, en_actions, EVIDENCE))
check("Arabic report uses the person's Arabic name", "عمر أحمد" in generate_from_template(NAMED, ar_actions, EVIDENCE, "ar", PLUGIN))
check("Email says who was recognised, only when someone was",
      "Recognised by the camera: Omar Ahmed" in email_template.facts(NAMED) and
      not any("Recognised" in f for f in email_template.facts(INCIDENT)))
check("A person's name can't inject HTML into the email",
      "<script>" not in email_template.html_body(
          {**NAMED, "metadata": {**NAMED["metadata"], "people": [{"person_id": "x", "person_name": "<script>x</script>"}]}},
          generate_from_template(NAMED, en_actions, EVIDENCE), en_actions, None, False))

SUMMARY = {
    "tz": "Africa/Cairo", "total": 12, "by_status": {"open": 3, "acknowledged": 2, "resolved": 7},
    "top_type": {"key": "PPE_MISSING", "count": 7}, "top_zone": {"key": "Excavation Edge", "count": 5},
    "busiest_hour": 10, "median_minutes_to_handle": 4.2, "open_total": 4,
    "open": [{**INCIDENT, "received_at": INCIDENT["timestamp"]}],
}
check("Summary is due once the time has passed, once a day",
      digest.due(datetime(2026, 10, 11, 18, 5), None, "18:00")
      and not digest.due(datetime(2026, 10, 11, 17, 59), None, "18:00")
      and not digest.due(datetime(2026, 10, 11, 19, 0), "2026-10-11", "18:00")
      and not digest.due(datetime(2026, 10, 11, 19, 0), None, ""))
lines = digest.sentences(SUMMARY, "en", PLUGIN)
check("Summary in plain sentences", lines == [
    "12 incidents today, 3 still waiting for someone.",
    "Most common: missing safety gear (7), mostly at Excavation Edge.",
    "Busiest time: around 10 AM.",
    "Half were picked up within 4 minutes."])
check("Summary subject", digest.subject(SUMMARY, "en") == "Today on site: 12 incidents, 3 still open")
summary_html = digest.html_body(SUMMARY, "en", PLUGIN)
check("Summary lists what is still open, and how many more", "Worker without a hard hat" in summary_html and "and 3 more" in summary_html)
quiet = {**SUMMARY, "total": 0, "by_status": {"open": 0}, "open": [], "open_total": 0}
check("A quiet day says so", digest.sentences(quiet, "en", PLUGIN) == ["No incidents in the last 24 hours."]
      and digest.subject(quiet, "en") == "Today on site: a quiet day")
ar_lines = digest.sentences(SUMMARY, "ar", PLUGIN)
ar_html = digest.html_body(SUMMARY, "ar", PLUGIN)
check("Arabic summary: right-to-left, Arabic names and times",
      'dir="rtl"' in ar_html and "letter-spacing" not in ar_html and "حافة الحفرة" in ar_lines[1]
      and ar_lines[2] == "أكثر الأوقات ازدحامًا: نحو الساعة 10 صباحًا." and "عامل بدون خوذة" in ar_html)

# ---------- regulation clauses (plugin rule "regulations", added by code after the report) ----------
CITE = {"document": "OSHJ-CoP-04", "clause": "5.5.3", "heading": "Guard Rail Systems", "page": 10,
        "text": "Guard rails shall be at least 950 mm high.", "heading_ar": "أنظمة الحواجز", "text_ar": "نص البند",
        "url": "https://example.org/cop-04.pdf"}
cited = {"rules": [{"rule_id": "RULE_X", "regulations": [CITE, {"document": "no clause"}]}]}
check("A rule's citations are read from the plugin, incomplete ones skipped",
      rule_regulations(cited, "RULE_X") == [CITE] and rule_regulations(cited, "RULE_Y") == [])
report_en = with_regulations(generate_from_template(INCIDENT, en_actions, EVIDENCE, "en", PLUGIN), [CITE], "en")
check("Regulation section sits between Violations and Findings, word for word",
      report_en.index("## Violations") < report_en.index("## Regulation") < report_en.index("## Findings")
      and '**OSHJ-CoP-04, clause 5.5.3 "Guard Rail Systems", page 10**: Guard rails shall be at least 950 mm high.'
      in report_en and "Source: https://example.org/cop-04.pdf" in report_en)
check("A report with a Regulation section still has every required section", not missing_sections(report_en, "en"))
report_ar = with_regulations(generate_from_template(INCIDENT, ar_actions, EVIDENCE, "ar", PLUGIN), [CITE], "ar")
check("Arabic report uses the Arabic clause text", "## اللائحة" in report_ar and "البند 5.5.3 «أنظمة الحواجز»" in report_ar
      and "نص البند" in report_ar and not missing_sections(report_ar, "ar"))
plain = generate_from_template(INCIDENT, en_actions, EVIDENCE, "en", PLUGIN)
english_only = with_regulations(plain, [{k: v for k, v in CITE.items() if k != "text_ar"}], "ar")
check("Arabic report says when the clause is quoted in English", "(النص الأصلي بالإنجليزية)" in english_only)
check("No citations, no section; added only once", with_regulations(plain, [], "en") == plain
      and with_regulations(report_en, [CITE], "en") == report_en)

# ---------- Gemini writes the report (stub client: no network) ----------
from report import generate_with_gemini   # noqa: E402


class _Models:
    def __init__(self, text):
        self.text, self.calls = text, []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        return type("R", (), {"text": self.text, "candidates": []})()


class _Gemini:
    def __init__(self, text):
        self.models = _Models(text)


ok_text = generate_from_template(INCIDENT, en_actions, EVIDENCE, "en", PLUGIN)
g = _Gemini(ok_text)
out = generate_with_gemini(g, INCIDENT, PLUGIN, en_actions, EVIDENCE, "en")
model, contents, config = g.models.calls[0]
check("Gemini gets the same facts and rules as Claude", out == ok_text and model.startswith("gemini")
      and "evt_test01" in contents and "Do not invent" in config.system_instruction)
try:
    generate_with_gemini(_Gemini(""), INCIDENT, PLUGIN, en_actions, EVIDENCE, "en")
    check("An empty Gemini answer is an error (so the template is used)", False)
except RuntimeError:
    check("An empty Gemini answer is an error (so the template is used)", True)

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
