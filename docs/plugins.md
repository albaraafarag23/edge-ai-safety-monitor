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
| `classes` | `{class_name: {"confidence": x}}`. Only these classes are detected and sent on |
| `extra_models` | Optional list of more models run on the same frames, each with its own `model`, `imgsz`, `default_confidence` and `classes` (e.g. `smoking.pt` for `cigarette`). Their detections are merged into one message; `model` in the message becomes `construction_ppe.pt+smoking.pt`. Optional `every_n_frames` (default 1) runs an extra model only on every n-th frame and reuses its last result in between, to save time on slow-changing things like smoking |

Model files live in `models/` (mounted at `/models` in Docker; git-ignored). Each extra model costs
another inference per frame, so check the FPS on the Jetson when adding one.

## `zones` section
`{zone_id: {"name", "camera_id", "polygon": [[x, y], ...]}}` in pixels of that camera's image.
A person is "in" a zone when the bottom-centre of their box (their feet) is inside the polygon.
Admins and supervisors can redraw a zone on the camera picture in the console (Live cameras, "Edit zones"), for
example once the camera is mounted. The drawing is stored as fractions of the picture (0-1) in Postgres
(`zone_settings`) and the Redis hash `zones:settings:<plugin_id>`; the event engine scales it to each detection's
`frame_size`, so it fits any camera resolution. "Back to the original shape" deletes it and the plugin polygon
applies again (`backend/zone_settings.py`, `GET /zones`, `PUT` / `DELETE /zones/{zone_id}`).

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
shown in the console).

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

## Startup checks
- A class missing from the model prints a warning and is skipped.
- A rule using a class not in `detection.classes` stops startup (disabled rules are skipped).
- A missing model file stops live mode with a clear message (test mode needs no model).
- A rule whose trigger classes can't be detected by the model stops startup.

Check a plugin against a model without running the pipeline:

    cd cv_pipeline
    python plugin_config.py ../plugins construction_safety ..
