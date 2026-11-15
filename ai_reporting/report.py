"""Turns an incident payload into a Markdown report for the site supervisor, in English and (optionally) Arabic.

The report uses only the incident's own fields plus the recommended actions the plugin
approves for that rule, so the LLM has nothing to invent from. If Claude is unavailable
(no API key, network error, refusal) the same structure is filled from a template.

Each language is its own request with the same facts (not a translation of the English report), so each
can be checked for its sections on its own. Arabic names for rules, zones and approved actions come from the
plugin's `translations.ar` block (docs/plugins.md).
"""
import json

import anthropic

MODEL = "claude-opus-5-5"
LANGUAGES = ("en", "ar")
SECTIONS = {
    "en": ["Summary", "Violations", "Findings", "Recommended Actions"],
    "ar": ["الملخص", "المخالفات", "النتائج", "الإجراءات الموصى بها"],
}
NOT_SPECIFIED = {"en": "NOT SPECIFIED", "ar": "غير محدد"}

SYSTEM_PROMPT = """You write safety incident reports for {audience} at a site monitored by "{plugin_name}".
Tone: {tone}.

You receive one incident as JSON, the recommended actions the site has approved for the rule
that fired, and which evidence files are attached. Write the report from these inputs only.

Rules:
- State only facts present in the inputs. Do not invent or guess causes, names, identities,
  injuries, intentions, weather, or anything else not in the JSON.
- Where a field is missing, null or empty, write "NOT SPECIFIED".
- People: metadata.people lists who the cameras' face recognition identified (it may be empty). Name only
  those people, and say the identification is automatic and should be confirmed. Never name anyone else.
- Recommended actions: choose 2-3 from the approved list. You may adjust wording to fit the
  incident, but do not add actions that are not on the list. If the list is empty, write
  "NOT SPECIFIED".
- Times are UTC; keep them as given.
- Do not cite laws, codes or regulations: the system adds the exact clause for the rule after your report.

Output only the report, in Markdown, with exactly this structure:
# Safety Incident Report: <event_type in plain words>
## Summary
2-3 sentences: what happened, where, when, how serious.
## Violations
One bullet per entry in rules_violated.
## Findings
Bullets: event ID, time, camera, location, duration, severity, detected entities,
missing equipment, people identified, evidence attached.
## Recommended Actions
A numbered list of 2-3 actions."""

SYSTEM_PROMPT_AR = """You write safety incident reports in Arabic for {audience} at a site monitored by "{plugin_name}".
Tone: {tone}. Write clear Modern Standard Arabic that a site supervisor in Egypt reads easily.

You receive one incident as JSON (its field values are in English), the Arabic names to use for its
type, rule, zone and detected items, the recommended actions the site has approved (in Arabic), and
which evidence files are attached. Write the report from these inputs only.

Rules:
- State only facts present in the inputs. Do not invent or guess causes, names, identities,
  injuries, intentions, weather, or anything else not in the JSON.
- Where a field is missing, null or empty, write "غير محدد".
- People: metadata.people lists who the cameras' face recognition identified (it may be empty). Name only
  those people (use person_name_ar when it is given), and say the identification is automatic and should be
  confirmed. Never name anyone else.
- Use the Arabic names you are given. Keep identifiers exactly as they are, in Latin letters:
  event ID, camera ID, rule IDs, model and file names.
- Use Western digits (0-9). Times are UTC; keep them as given and say they are UTC.
- Do not cite laws, codes or regulations: the system adds the exact clause for the rule after your report.
- Recommended actions: choose 2-3 from the approved Arabic list. You may adjust wording to fit the
  incident, but do not add actions that are not on the list. If the list is empty, write "غير محدد".

Output only the report, in Markdown, with exactly this structure:
# تقرير حادثة سلامة: <نوع الحادثة بكلمات واضحة>
## الملخص
2-3 sentences: what happened, where, when, how serious.
## المخالفات
One bullet per entry in rules_violated (rule ID, then the Arabic description).
## النتائج
Bullets: event ID, time, camera, location, duration, severity, detected entities,
missing equipment, evidence attached.
## الإجراءات الموصى بها
A numbered list of 2-3 actions."""

# Arabic names for codes the incident carries (the console uses the same words, frontend/src/lib/terms.ts)
EVENT_TYPE_AR = {
    "PPE_MISSING": "معدات وقاية ناقصة",
    "RESTRICTED_ZONE_ENTRY": "دخول منطقة محظورة",
    "LOITERING_HAZARD_ZONE": "البقاء في منطقة خطرة",
    "ZONE_OVER_CAPACITY": "تجاوز سعة المنطقة",
    "PERSON_NEAR_MACHINERY": "شخص قرب آلة",
    "SMOKING": "التدخين",
    "VAPING": "السجائر الإلكترونية",
    "FOOD_IN_RESTRICTED_ZONE": "طعام أو شراب في منطقة محظورة",
    "PERSON_DOWN": "سقوط شخص",
    "SLEEPING_ON_SITE": "النوم في الموقع",
}
SEVERITY_AR = {"CRITICAL": "حرجة", "HIGH": "مرتفعة", "MEDIUM": "متوسطة", "LOW": "منخفضة"}
ITEM_AR = {"hard_hat": "خوذة", "safety_vest": "سترة عاكسة"}
CLASS_AR = {
    "Person": "شخص", "Hardhat": "خوذة", "NO-Hardhat": "بدون خوذة", "Safety Vest": "سترة عاكسة",
    "NO-Safety Vest": "بدون سترة", "machinery": "آلات", "vehicle": "مركبة", "cigarette": "سيجارة", "smoking": "تدخين",
    "vape": "سيجارة إلكترونية", "bottle": "زجاجة", "cup": "كوب",
}
EVIDENCE_AR = {"snapshot": "لقطة", "video_clip": "مقطع فيديو"}


def plugin_ar(plugin: dict) -> dict:
    return (plugin.get("translations") or {}).get("ar") or {}


def approved_actions(plugin: dict, rule_id: str | None, lang: str) -> list[str]:
    """The rule's approved actions in `lang`; English when there is no translation."""
    rule = next((r for r in plugin.get("rules", []) if r.get("rule_id") == rule_id), {})
    english = rule.get("recommended_actions", [])
    if lang == "ar":
        return (plugin_ar(plugin).get("rules", {}).get(rule_id) or {}).get("recommended_actions") or english
    return english


def arabic_names(incident: dict, plugin: dict) -> dict:
    """The Arabic words for this incident's codes, for the Arabic report and email."""
    meta = incident.get("metadata") or {}
    t = plugin_ar(plugin)
    rule_t = t.get("rules", {}).get(meta.get("rule_id")) or {}
    zone_id = meta.get("zone_id")
    zone = t.get("zones", {}).get(zone_id) if zone_id else None
    return {
        "event_type": EVENT_TYPE_AR.get(incident.get("event_type"), human(incident.get("event_type"))),
        "severity": SEVERITY_AR.get(incident.get("severity"), incident.get("severity")),
        "rule_name": rule_t.get("name"),
        "rule_description": rule_t.get("description"),
        "location": zone or (None if incident.get("location") in (None, "", "NOT SPECIFIED") else incident.get("location")),
        "missing_equipment": [ITEM_AR.get(m, m) for m in meta.get("missing_equipment") or []],
        "detected_entities": [CLASS_AR.get(c, c) for c in meta.get("detected_entities") or []],
    }


def people_names(incident: dict, lang: str = "en") -> list[str]:
    """Who face recognition identified in the incident (metadata.people, contracts v2.6)."""
    people = (incident.get("metadata") or {}).get("people") or []
    return [str((p.get("person_name_ar") if lang == "ar" else None) or p.get("person_name"))
            for p in people if isinstance(p, dict) and p.get("person_name")]


def _llm_input(incident: dict) -> dict:
    """The incident without pixel coordinates, which don't help a reader."""
    meta = dict(incident.get("metadata") or {})
    meta["objects_involved"] = [
        {k: v for k, v in o.items() if k in ("class_name", "confidence", "missing_equipment")}
        for o in meta.get("objects_involved") or []
    ]
    return {**incident, "metadata": meta}


def generate_with_claude(client: anthropic.Anthropic, incident: dict, plugin: dict,
                         actions: list[str], evidence: dict, lang: str = "en") -> str:
    report_cfg = plugin.get("report", {})
    prompt = SYSTEM_PROMPT_AR if lang == "ar" else SYSTEM_PROMPT
    plugin_name = plugin.get("name", plugin.get("plugin_id", "NOT SPECIFIED"))
    if lang == "ar":
        plugin_name = plugin_ar(plugin).get("plugin_name", plugin_name)
    system = prompt.format(
        audience=report_cfg.get("audience", "the site supervisor"),
        plugin_name=plugin_name,
        tone=report_cfg.get("tone", "formal and factual"),
    )
    user = f"Incident JSON:\n{json.dumps(_llm_input(incident), indent=2)}\n\n"
    if lang == "ar":
        user += f"Arabic names to use:\n{json.dumps(arabic_names(incident, plugin), indent=2, ensure_ascii=False)}\n\n"
    user += (
        f"Approved recommended actions for {(incident.get('metadata') or {}).get('rule_id', 'this rule')}:\n"
        f"{json.dumps(actions, indent=2, ensure_ascii=False)}\n\n"
        f"Evidence attached: {json.dumps(evidence)}"
    )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium"},
        # if a safety classifier declines, re-run on Anthropic's recommended fallback model
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to write the report ({response.stop_details})")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError(f"Claude returned no text (stop_reason={response.stop_reason})")
    return text


def human(event_type: str) -> str:
    """PPE_MISSING -> "PPE missing", PERSON_NEAR_MACHINERY -> "Person near machinery"."""
    words = [w if w in ("PPE",) else w.lower() for w in (event_type or "").split("_")]
    text = " ".join(words)
    return text[:1].upper() + text[1:] if text else "Safety incident"


def _ns(value, lang: str = "en") -> str:
    return NOT_SPECIFIED[lang] if value in (None, "", []) else str(value)


def generate_from_template(incident: dict, actions: list[str], evidence: dict, lang: str = "en",
                           plugin: dict | None = None) -> str:
    if lang == "ar":
        return _template_ar(incident, actions, evidence, plugin or {})
    meta = incident.get("metadata") or {}
    attached = [name for name, ok in evidence.items() if ok]
    lines = [
        f"# Safety Incident Report: {human(incident.get('event_type'))}",
        "## Summary",
        f"{human(incident.get('event_type'))} (severity {_ns(incident.get('severity'))}) was detected on camera "
        f"{_ns(incident.get('camera_id'))}, location {_ns(incident.get('location'))}, at "
        f"{_ns(incident.get('timestamp'))} UTC. The condition lasted {_ns(incident.get('duration_seconds'))} seconds "
        f"before the alert.",
        "## Violations",
        *[f"- {v}" for v in incident.get("rules_violated") or ["NOT SPECIFIED"]],
        "## Findings",
        f"- Event ID: {_ns(incident.get('event_id'))}",
        f"- Time (UTC): {_ns(incident.get('timestamp'))}",
        f"- Camera: {_ns(incident.get('camera_id'))}",
        f"- Location: {_ns(incident.get('location'))}",
        f"- Duration: {_ns(incident.get('duration_seconds'))} s",
        f"- Severity: {_ns(incident.get('severity'))}",
        f"- Detected entities: {_ns(', '.join(meta.get('detected_entities') or []))}",
        f"- Missing equipment: {_ns(', '.join(meta.get('missing_equipment') or []))}",
        f"- People identified (automatic face recognition, to be confirmed): "
        f"{_ns(', '.join(people_names(incident)))}",
        f"- Evidence attached: {_ns(', '.join(attached))}",
        "## Recommended Actions",
        *([f"{i}. {a}" for i, a in enumerate(actions[:3], 1)] or ["NOT SPECIFIED"]),
    ]
    return "\n".join(lines)


def _template_ar(incident: dict, actions: list[str], evidence: dict, plugin: dict) -> str:
    names = arabic_names(incident, plugin)
    ns = lambda v: _ns(v, "ar")  # noqa: E731
    attached = [EVIDENCE_AR.get(name, name) for name, ok in evidence.items() if ok]
    rules_t = plugin_ar(plugin).get("rules", {})

    def violation(line: str) -> str:
        # "RULE_PPE_01: Hard hat required on site" -> the rule's Arabic description
        rule_id, _, english = line.partition(": ")
        return f"{rule_id}: {(rules_t.get(rule_id) or {}).get('description') or english}" if english else line

    lines = [
        f"# تقرير حادثة سلامة: {names['event_type']}",
        "## الملخص",
        f"رُصدت حادثة «{names['event_type']}» (الخطورة: {ns(names['severity'])}) على الكاميرا "
        f"{ns(incident.get('camera_id'))}، في الموقع: {ns(names['location'])}، بتاريخ {ns(incident.get('timestamp'))} "
        f"(بالتوقيت العالمي UTC). استمرت الحالة {ns(incident.get('duration_seconds'))} ثانية قبل التنبيه.",
        "## المخالفات",
        *[f"- {violation(v)}" for v in incident.get("rules_violated") or [NOT_SPECIFIED["ar"]]],
        "## النتائج",
        f"- رقم الحادثة: {ns(incident.get('event_id'))}",
        f"- الوقت (UTC): {ns(incident.get('timestamp'))}",
        f"- الكاميرا: {ns(incident.get('camera_id'))}",
        f"- الموقع: {ns(names['location'])}",
        f"- المدة: {ns(incident.get('duration_seconds'))} ثانية",
        f"- الخطورة: {ns(names['severity'])}",
        f"- ما رُصد: {ns('، '.join(names['detected_entities']))}",
        f"- المعدات الناقصة: {ns('، '.join(names['missing_equipment']))}",
        f"- من تم التعرف عليهم (تعرّف آلي على الوجه، يحتاج إلى تأكيد): {ns('، '.join(people_names(incident, 'ar')))}",
        f"- الأدلة المرفقة: {ns('، '.join(attached))}",
        "## الإجراءات الموصى بها",
        *([f"{i}. {a}" for i, a in enumerate(actions[:3], 1)] or [NOT_SPECIFIED["ar"]]),
    ]
    return "\n".join(lines)


REGULATION_HEADING = {"en": "Regulation", "ar": "اللائحة"}
REGULATION_WORDS = {
    "en": {"clause": "clause", "page": "page", "source": "Source"},
    "ar": {"clause": "البند", "page": "صفحة", "source": "المصدر"},
}


def rule_regulations(plugin: dict, rule_id: str | None) -> list[dict]:
    """The regulation clauses a plugin rule cites (`regulations` in the rule, docs/plugins.md)."""
    rule = next((r for r in plugin.get("rules", []) if r.get("rule_id") == rule_id), {})
    return [c for c in rule.get("regulations") or [] if isinstance(c, dict) and c.get("document") and c.get("clause")]


def regulation_section(citations: list[dict], lang: str = "en") -> str:
    """'## Regulation': each clause the rule breaks, word for word as the plugin stores it (looked up once with
    SiteSentry Regs, see docs/regulations.md). Written by code, never by the LLM, so a clause can't be invented.
    Arabic reports use the clause's Arabic text where the code of practice has an Arabic edition."""
    w = REGULATION_WORDS[lang]
    lines = [f"## {REGULATION_HEADING[lang]}"]
    for c in citations:
        heading = (c.get("heading_ar") if lang == "ar" else None) or c.get("heading") or ""
        text = (c.get("text_ar") if lang == "ar" else None) or c.get("text") or ""
        if lang == "ar" and text and not c.get("text_ar"):
            text += " (النص الأصلي بالإنجليزية)"   # the code of practice has no clean Arabic wording
        where = f"{c['document']}, {w['clause']} {c['clause']}" + (f" «{heading}»" if lang == "ar" and heading
                                                                    else f' "{heading}"' if heading else "")
        if c.get("page"):
            where += f", {w['page']} {c['page']}"
        lines.append(f"- **{where}**" + (f": {text}" if text else ""))
        if c.get("url"):
            lines.append(f"  {w['source']}: {c['url']}")
    return "\n".join(lines)


def with_regulations(markdown: str, citations: list[dict], lang: str = "en") -> str:
    """The report with its Regulation section after Violations (or at the end), when the rule cites any."""
    if not citations or f"## {REGULATION_HEADING[lang]}" in markdown:
        return markdown
    section = regulation_section(citations, lang)
    after = f"## {SECTIONS[lang][2]}"    # Findings: the section goes just before it, after Violations
    if after in markdown:
        head, tail = markdown.split(after, 1)
        return f"{head.rstrip()}\n\n{section}\n\n{after}{tail}"
    return f"{markdown.rstrip()}\n\n{section}\n"


def missing_sections(markdown: str, lang: str = "en") -> list[str]:
    return [s for s in SECTIONS[lang] if f"## {s}" not in markdown]
