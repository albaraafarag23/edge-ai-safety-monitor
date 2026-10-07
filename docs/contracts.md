# Interface contracts

Version 2.1 (2026-10-07): construction domain, plugin-driven detection, incident media.
Don't change these without telling the team. Any change must update every service that
reads or writes the message, plus `event_engine/test_rules.py`.

## Transport
Both messages travel over Redis streams. Each stream entry has one field, `data`, holding
the whole message as JSON:

| Stream | Producer → consumers | Message |
|---|---|---|
| `detections` | `cv_pipeline` → `event_engine` | Detection output |
| `incidents` | `event_engine` → `backend`, `ai_reporting` | Incident payload |

Timestamps are UTC ISO 8601 (`2026-10-07T13:30:00.125Z`). Boxes are `[x1, y1, x2, y2]`
in pixels of the original camera frame.

## Detection output (one per frame)
```json
{
  "timestamp": "2026-10-07T13:30:00.125Z",
  "camera_id": "cam_01",
  "frame_id": 10425,
  "plugin_id": "construction_safety",
  "model": "construction_ppe.pt",
  "frame_size": [1920, 1080],
  "detections": [
    {"detection_id": "det_001", "class_name": "Person", "confidence": 0.92,
     "bbox": [812.0, 340.5, 951.2, 760.0], "attributes": {}},
    {"detection_id": "det_002", "class_name": "NO-Hardhat", "confidence": 0.81,
     "bbox": [850.3, 340.5, 905.0, 392.8], "attributes": {}}
  ]
}
```
| Field | Notes |
|---|---|
| `frame_id` | Counts up from 1 each time the detector starts |
| `plugin_id` | Selects the plugin in `plugins/` (which classes, thresholds and rules apply) |
| `detections` | Only the plugin's classes, above that class's confidence threshold. Empty list if none |
| `detection_id` | Unique within the frame only (`det_001`, `det_002`, …) |
| `class_name` | Exactly as the model names it, e.g. `Person`, `Hardhat`, `NO-Hardhat`, `machinery` |
| `attributes` | Reserved for per-object extras (tracking id, pose keypoints). Empty for now |

PPE is sent as separate boxes (`Hardhat`, `NO-Hardhat`, …). The event engine matches them
to people (see `ppe` rules in `docs/plugins.md`). The detector doesn't set `hard_hat: false`
attributes itself.

## Incident payload (one per fired rule)
```json
{
  "event_id": "evt_3f9a1c2b7d4e",
  "timestamp": "2026-10-07T13:30:03.125Z",
  "plugin_id": "construction_safety",
  "camera_id": "cam_01",
  "severity": "HIGH",
  "event_type": "PPE_MISSING",
  "location": "Excavation Edge",
  "duration_seconds": 3.0,
  "rules_violated": ["RULE_PPE_01: Hard hat and safety vest required on site"],
  "snapshot_url": "/media/snapshots/evt_3f9a1c2b7d4e.jpg",
  "clip_url": "/media/clips/evt_3f9a1c2b7d4e.mp4",
  "metadata": {
    "rule_id": "RULE_PPE_01",
    "zone_id": "excavation_edge",
    "zone_name": "Excavation Edge",
    "detected_entities": ["Person"],
    "missing_equipment": ["hard_hat"],
    "objects_involved": [
      {"detection_id": "det_001", "class_name": "Person", "confidence": 0.92,
       "bbox": [812.0, 340.5, 951.2, 760.0], "attributes": {}, "missing_equipment": ["hard_hat"]}
    ],
    "frame_id": 10431,
    "model": "construction_ppe.pt"
  }
}
```
| Field | Notes |
|---|---|
| `event_id` | `evt_` + 12 hex characters, unique |
| `timestamp` | Time of the frame on which the rule fired |
| `severity` | `LOW`, `MEDIUM`, `HIGH` or `CRITICAL` (set per rule in the plugin) |
| `event_type` | Set per rule in the plugin, e.g. `PPE_MISSING`, `RESTRICTED_ZONE_ENTRY`, `LOITERING_HAZARD_ZONE`, `ZONE_OVER_CAPACITY`, `PERSON_NEAR_MACHINERY` |
| `location` | Zone name, or `"NOT SPECIFIED"` for rules without a zone |
| `duration_seconds` | How long the condition had lasted when the rule fired |
| `rules_violated` | `"<rule_id>: <description>"` strings |
| `snapshot_url` | Annotated frame the rule fired on. Path on the backend (`GET /media/...`) and under the shared `media/` folder |
| `clip_url` | Video from ~5 s before to ~3 s after. Same location rules as `snapshot_url` |
| `metadata.zone_id`, `metadata.zone_name` | `null` for rules without a zone |
| `metadata.missing_equipment` | Empty list for non-PPE rules |

The event engine sets `snapshot_url` and `clip_url` when it creates the incident. The detector
for that camera writes the files a moment later: the snapshot right away, the clip about 3 s later.
Consumers must allow for the file not existing yet, or never existing (e.g. the detector restarted).

The backend's `GET /incidents` and `GET /incidents/{event_id}` return this payload, plus
`received_at` (when the backend stored it).

## Report (ai_reporting → backend)
`POST /reports`, read back with `GET /incidents/{event_id}/report` or `GET /reports`:
```json
{
  "event_id": "evt_3f9a1c2b7d4e",
  "markdown": "# Safety Incident Report: ...",
  "generated_by": "claude-opus-5-5",
  "delivery": {"status": "sent", "recipients": ["supervisor@example.com"],
               "attachments": ["evt_3f9a1c2b7d4e.jpg", "evt_3f9a1c2b7d4e.mp4"], "error": null}
}
```
`generated_by` is a model id, `"template"` (Claude unavailable), or `"duplicate"`. A repeat of the
same rule on the same camera within the cooldown isn't re-sent: `delivery.status` is
`"suppressed_duplicate"`. Other statuses: `sent`, `failed`, `not_configured`.
