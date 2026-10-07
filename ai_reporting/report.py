"""Turns an incident payload into a Markdown report for the site supervisor.

The report uses only the incident's own fields plus the recommended actions the plugin
approves for that rule, so the LLM has nothing to invent from. If Claude is unavailable
(no API key, network error, refusal) the same structure is filled from a template.
"""
import json

import anthropic

MODEL = "claude-opus-5-5"
SECTIONS = ["Summary", "Violations", "Findings", "Recommended Actions"]

SYSTEM_PROMPT = """You write safety incident reports for {audience} at a site monitored by "{plugin_name}".
Tone: {tone}.

You receive one incident as JSON, the recommended actions the site has approved for the rule
that fired, and which evidence files are attached. Write the report from these inputs only.

Rules:
- State only facts present in the inputs. Do not invent or guess causes, names, identities,
  injuries, intentions, weather, or anything else not in the JSON.
- Where a field is missing, null or empty, write "NOT SPECIFIED".
- Recommended actions: choose 2-3 from the approved list. You may adjust wording to fit the
  incident, but do not add actions that are not on the list. If the list is empty, write
  "NOT SPECIFIED".
- Times are UTC; keep them as given.

Output only the report, in Markdown, with exactly this structure:
# Safety Incident Report: <event_type in plain words>
## Summary
2-3 sentences: what happened, where, when, how serious.
## Violations
One bullet per entry in rules_violated.
## Findings
Bullets: event ID, time, camera, location, duration, severity, detected entities,
missing equipment, evidence attached.
## Recommended Actions
A numbered list of 2-3 actions."""


def _llm_input(incident: dict) -> dict:
    """The incident without pixel coordinates, which don't help a reader."""
    meta = dict(incident.get("metadata") or {})
    meta["objects_involved"] = [
        {k: v for k, v in o.items() if k in ("class_name", "confidence", "missing_equipment")}
        for o in meta.get("objects_involved") or []
    ]
    return {**incident, "metadata": meta}


def generate_with_claude(client: anthropic.Anthropic, incident: dict, plugin: dict,
                         actions: list[str], evidence: dict) -> str:
    report_cfg = plugin.get("report", {})
    system = SYSTEM_PROMPT.format(
        audience=report_cfg.get("audience", "the site supervisor"),
        plugin_name=plugin.get("name", plugin.get("plugin_id", "NOT SPECIFIED")),
        tone=report_cfg.get("tone", "formal and factual"),
    )
    user = (
        f"Incident JSON:\n{json.dumps(_llm_input(incident), indent=2)}\n\n"
        f"Approved recommended actions for {(incident.get('metadata') or {}).get('rule_id', 'this rule')}:\n"
        f"{json.dumps(actions, indent=2)}\n\n"
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


def _ns(value) -> str:
    return "NOT SPECIFIED" if value in (None, "", []) else str(value)


def generate_from_template(incident: dict, actions: list[str], evidence: dict) -> str:
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
        f"- Evidence attached: {_ns(', '.join(attached))}",
        "## Recommended Actions",
        *([f"{i}. {a}" for i, a in enumerate(actions[:3], 1)] or ["NOT SPECIFIED"]),
    ]
    return "\n".join(lines)


def missing_sections(markdown: str) -> list[str]:
    return [s for s in SECTIONS if f"## {s}" not in markdown]
