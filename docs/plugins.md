# Plugins

A plugin is one JSON file in `plugins/`. It controls both what the Jetson detects
and which rules the event engine applies. Both containers mount the same folder,
and `PLUGIN_ID` picks the plugin to use.

## `detection` section (read by `cv_pipeline`)
| Field | Meaning |
|---|---|
| `model` | Model file inside `MODELS_DIR` (set `MODEL_PATH` to override, e.g. a TensorRT `.engine`) |
| `imgsz` | Inference image size |
| `default_confidence` | Threshold for classes that don't set their own |
| `classes` | `{class_name: {"confidence": x, "max_width": w}}`. Only these classes are detected and sent on. Optional `max_width` (0-1, fraction of the frame width) drops boxes wider than any real one: `Person` uses 0.6, because a dark, grainy empty room once came back as one frame-wide "Person" at 0.8 confidence |
| `extra_models` | Optional list of more models run on the same frames, each with its own `model`, `imgsz`, `default_confidence` and `classes` (e.g. `smoking.pt` for `cigarette`). Their detections are merged into one message; `model` in the message becomes `construction_ppe.pt+smoking.pt`. Optional `every_n_frames` (default 1) runs an extra model only on every n-th frame and reuses its last result in between, to save time on slow-changing things like smoking. An extra model with `crop_from` (e.g. `"Person"`) is a classifier, not a detector: it classifies a head-and-upper-body crop of each of the main model's boxes of that class (`crop`: crop size it was trained on, default 384; `imgsz`: its input size) and sends that region as a box of each class over its threshold. `smoking_act.pt` works this way and sends `smoking` |

Model files live in `models/` (mounted at `/models` in Docker; git-ignored). Each extra model costs
another inference per frame, so check the FPS on the Jetson when adding one.

## `zones` section
`{zone_id: {"name", "camera_id", "polygon": [[x, y], ...]}}` in pixels of that camera's image.
A person is "in" a zone when the bottom-centre of their box (their feet) is inside the polygon.
With several cameras, a zone belongs to the camera named in its `camera_id` (to every camera if it has none):
each camera looks at a different part of the site, so on any other camera the zone doesn't exist, and rules that
need it stay quiet there, until someone draws it for that camera.

Admins and supervisors draw zones on a camera's picture in the console (Live cameras, pick the camera, "Edit
zones"), for example once the camera is mounted, or to put an existing zone on a second camera. A drawing is
stored per camera as fractions of the picture (0-1) in Postgres (`zone_drawings`) and the Redis hash
`zones:settings:<plugin_id>`; the event engine scales it to each detection's `frame_size`, so it fits any camera
resolution. "Back to the original shape" (or "Remove from this camera") deletes the drawing
(`backend/zone_settings.py`, `GET /zones?camera_id=`, `PUT` / `DELETE /zones/{zone_id}?camera_id=`).

## `rules` section (read by `event_engine`)
| `type` | Fires when | Extra fields |
|---|---|---|
| `zone` | `subject_classes` inside `zone` | `max_count`: fire only when more than N are inside |
| `proximity` | a subject is close to one of `near_classes` | `max_gap_ratio`: gap limit as a fraction of the subject's box height (default 0.5); optional `zone` |
| `ppe` | a subject is missing an item in `required` | each item has `name`, `present_classes` (worn) and/or `absent_classes` (e.g. `NO-Hardhat`); optional `zone` |
| `presence` | one of `subject_classes` is visible at all (e.g. a cigarette) | optional `zone` |

Common fields: `rule_id`, `description`, `event_type`, `severity`, `min_duration_s` (condition must last
this long; loitering = zone rule with a long duration), `grace_s` (detector dropouts shorter than this
don't reset the timer, default 1), `cooldown_s` (default 10), `active_hours` (see below), `name` (shown in the
console), `enabled` (false = not usable yet, e.g. the model lacks its classes), `planned` (true = not built
yet; its `type` may not exist yet and it isn't checked), `requires` (what an unusable rule still needs,
shown in the console), `regulations` (the code-of-practice clauses the rule enforces, quoted in every report
for it; see docs/regulations.md), `personal` (false = nobody is counted for it in the per-person tally, e.g.
a person down is someone in need, not a violation; capacity rules never count anyone).

One rule per thing a site may want to switch off: hard hat and vest are separate `ppe` rules
(`RULE_PPE_01`, `RULE_PPE_02`), smoking and vaping separate `presence` rules.

## Changing rules in the console
On the console's **Safety rules** page, admins and supervisors can switch any usable rule off and back on
(e.g. a site that doesn't care about smoking) and change its `min_duration_s`, `severity`, `cooldown_s`,
`max_count` (capacity rules) and `active_hours`. `active_hours` is
`{"start": "07:00", "end": "19:00", "days": [0, 1, 2, 3, 4]}` (Monday = 0) in site time (`SITE_TIMEZONE`,
default `Africa/Cairo`); an end before the start runs overnight and counts for the day the shift started.
Outside those hours the rule is quiet.

No restart is needed: the backend stores the changes in Postgres (`rule_settings` table, only the fields that
differ from the plugin) and mirrors them to the Redis hash `rules:settings:<plugin_id>` (`rule_id` → JSON),
which the event engine re-reads every 2 s. A rule that's off raises no incidents, reports or emails. Rules with
`"enabled": false` or `"planned": true` show under **Coming soon** and can't be changed.

Test the rules with synthetic frames:

    cd event_engine && python test_rules.py

## `translations` section (other languages)
Optional. The console's own text is translated in the frontend; text that comes from the plugin is translated
here, per language code (only `ar` for now):

```json
"translations": {
  "ar": {
    "plugin_name": "مراقبة سلامة مواقع البناء",
    "zones": { "excavation_edge": "حافة الحفرة" },
    "rules": {
      "RULE_PPE_01": {
        "name": "الخوذة",
        "description": "ارتداء الخوذة إلزامي في الموقع",
        "requires": "…",
        "recommended_actions": ["…", "…"]
      }
    }
  }
}
```

`GET /rules` returns the block (and a zone id → English name map) so the console can show rule and zone names in
the reader's language. Anything missing falls back to the English text. `recommended_actions` must be in the same
order as the English list; the Arabic version of the AI report picks from it. The detector and the rule engine
ignore this section.

## Words the plugin brings with it
So a new domain needs no change to the code, a plugin can name things itself (all optional):
- `report.person`: what its people are called in alert emails ("worker" by default; the hospital plugin says
  "staff member"), and `translations.ar.person` for Arabic.
- `translations.ar.items`: Arabic for the `name` of each required item (`"mask": "كمامة"`), used in incident
  titles, reports and emails. English shows the name itself with `_` as a space.
- `translations.ar.classes`: Arabic for the classes its models detect.

## The second plugin: `hospital_safety.json`
Infection control in a hospital, built to show that a new domain is a new file plus a model: the same four rule
types, no code specific to hospitals.

| Rule | What | State |
|---|---|---|
| `RULE_MASK_01`, `RULE_GOWN_01` | mask / gown required in the isolation room (`ppe`) | in use |
| `RULE_ZONE_01` | someone in the medication store (`zone`) | in use |
| `RULE_ZONE_02` | more than 3 people in the isolation room (`zone` with `max_count`) | in use |
| `RULE_SMOKE_01` | smoking anywhere (`presence`, the same smoking model as construction) | in use |
| `RULE_GLOVES_01`, `RULE_EYES_01` | gloves / goggles or face shield required in the isolation room (`ppe`) | in use since 2026-11-17 |
| `RULE_POSE_01` | patient fall | planned (needs a pose model) |

Model `models/medical_ppe.pt`: YOLO11s at 640 trained on CPPE-5 plus the Biosafety PPE set
(`training/build_medical_ppe3.py`: missing gloves / goggles labels filled in, black-and-white copies of the colour
photos because every Biosafety photo is black-and-white). A `ppe` rule fires when the item is *not* found on a
person, so `training/eval_hospital_rules.py` measures it per person: of the people wearing the item, how many the
model sees it on (163 colour photos / 217 lab photos): gloves 90% / 77%, goggles or face shield 85% / 76%, mask
91% / 82%, gown 91%. Hence the low thresholds in the plugin (gloves, goggles, face shield 0.15; mask, gown 0.3):
one sighting is enough. Not measured: people really without gloves or goggles (no photo set labels bare hands).
The previous model is `models/medical_ppe_v1.pt`. No regulation clauses are attached: SiteSentry Regs holds
construction codes only. Tests: `event_engine/test_hospital_plugin.py` (19).

Demo on a laptop, as its own copy of the stack (console at http://localhost:3006):

    docker compose -p hospital -f docker-compose.yml -f docker-compose.hospital-demo.yml up -d --build

It plays a video of the 29 CPPE-5 test photos as the camera (`python training/make_hospital_demo.py` makes it). Known false alarms seen in it: a full-face
respirator is not counted as a mask, and a person cut off at the picture's edge is judged on what is visible.

## Startup checks
- A class missing from the model prints a warning and is skipped.
- A rule using a class not in `detection.classes` stops startup (disabled rules are skipped).
- A missing model file stops live mode with a clear message (test mode needs no model).
- A rule whose trigger classes can't be detected by the model stops startup.

Check a plugin against a model without running the pipeline:

    cd cv_pipeline
    python plugin_config.py ../plugins construction_safety ..
