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

## `zones` section
`{zone_id: {"name", "camera_id", "polygon": [[x, y], ...]}}` in pixels of that camera's image.
A person is "in" a zone when the bottom-centre of their box (their feet) is inside the polygon.

## `rules` section (read by `event_engine`)
| `type` | Fires when | Extra fields |
|---|---|---|
| `zone` | `subject_classes` inside `zone` | `max_count`: fire only when more than N are inside |
| `proximity` | a subject is close to one of `near_classes` | `max_gap_ratio`: gap limit as a fraction of the subject's box height (default 0.5); optional `zone` |
| `ppe` | a subject is missing an item in `required` | each item has `name`, `present_classes` (worn) and/or `absent_classes` (e.g. `NO-Hardhat`); optional `zone` |

Common fields: `rule_id`, `description`, `event_type`, `severity`, `min_duration_s` (condition must last
this long; loitering = zone rule with a long duration), `grace_s` (detector dropouts shorter than this
don't reset the timer, default 1), `cooldown_s` (default 10), `enabled` (false = skipped everywhere).

Test the rules with synthetic frames:

    cd event_engine && python test_rules.py

## Startup checks
- A class missing from the model prints a warning and is skipped.
- A rule using a class not in `detection.classes` stops startup (disabled rules are skipped).
- A missing model file stops live mode with a clear message (test mode needs no model).
- A rule whose trigger classes can't be detected by the model stops startup.

Check a plugin against a model without running the pipeline:

    cd cv_pipeline
    python plugin_config.py ../plugins construction_safety ..
