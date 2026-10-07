"""Turns a plugin's "detection" section into the settings the detector runs with.

The plugin decides which model is loaded, which classes are kept and the
confidence threshold for each class. Rules are checked against what the model
can actually detect, so a rule that could never fire stops startup.
"""
import json
from dataclasses import dataclass
from pathlib import Path


class PluginError(Exception):
    pass


@dataclass
class DetectionConfig:
    plugin_id: str
    model_path: str
    imgsz: int
    class_ids: list[int]             # model class ids passed to YOLO
    thresholds: dict[str, float]     # class_name -> min confidence
    warnings: list[str]

    @property
    def min_confidence(self) -> float:
        return min(self.thresholds.values())

    def keep(self, class_name: str, confidence: float) -> bool:
        return confidence >= self.thresholds.get(class_name, 1.1)


def rule_classes(rule: dict) -> set[str]:
    """Every class a rule depends on. Keep in sync with event_engine/rules.py:rule_classes."""
    classes = set(rule.get("subject_classes", [])) | set(rule.get("near_classes", []))
    for item in rule.get("required", []):
        classes |= set(item.get("present_classes", [])) | set(item.get("absent_classes", []))
    return classes


def load_plugin(plugins_dir: str, plugin_id: str) -> dict:
    for path in Path(plugins_dir).glob("*.json"):
        with open(path) as f:
            plugin = json.load(f)
        if plugin.get("plugin_id") == plugin_id:
            return plugin
    raise PluginError(f"No plugin with plugin_id '{plugin_id}' in {plugins_dir}")


def build_config(plugin: dict, model_names: dict[int, str], models_dir: str = ".",
                 model_override: str | None = None) -> DetectionConfig:
    """model_names is the model's id -> class name map (YOLO(...).names)."""
    pid = plugin.get("plugin_id", "?")
    det = plugin.get("detection")
    if not det or not det.get("classes"):
        raise PluginError(f"[{pid}] plugin has no detection.classes section")

    default_conf = float(det.get("default_confidence", 0.4))
    name_to_id = {name: i for i, name in model_names.items()}
    warnings = []

    thresholds = {}
    for name, opts in det["classes"].items():
        if name not in name_to_id:
            warnings.append(f"[{pid}] class '{name}' is not in the model, it will never be detected")
            continue
        thresholds[name] = float((opts or {}).get("confidence", default_conf))

    if not thresholds:
        raise PluginError(f"[{pid}] none of the plugin's classes exist in the model "
                          f"(model classes: {sorted(name_to_id)})")

    for rule in plugin.get("rules", []):
        if not rule.get("enabled", True):
            continue
        triggers = rule_classes(rule)
        not_requested = triggers - set(det["classes"])
        if not_requested:
            raise PluginError(f"[{pid}] rule '{rule['rule_id']}' uses {sorted(not_requested)} "
                              f"which are missing from detection.classes")
        if not triggers & set(thresholds):
            raise PluginError(f"[{pid}] rule '{rule['rule_id']}' can never fire: none of "
                              f"{sorted(triggers)} can be detected by this model")

    return DetectionConfig(
        plugin_id=pid,
        model_path=_model_path(plugin, models_dir, model_override),
        imgsz=int(det.get("imgsz", 640)),
        class_ids=sorted(name_to_id[n] for n in thresholds),
        thresholds=thresholds,
        warnings=warnings,
    )


def _model_path(plugin: dict, models_dir: str, model_override: str | None) -> str:
    det = plugin.get("detection") or {}
    return model_override or str(Path(models_dir) / det.get("model", "yolo11n.pt"))


def model_path_for(plugin: dict, models_dir: str = ".", model_override: str | None = None) -> str:
    """Model path to load before build_config (the model is needed to read its class names)."""
    path = _model_path(plugin, models_dir, model_override)
    if not Path(path).exists():
        raise PluginError(f"[{plugin.get('plugin_id', '?')}] model file not found: {path} "
                          f"(train it first, or set MODEL_PATH to use another model)")
    return path


if __name__ == "__main__":
    # Check a plugin against a model without starting the pipeline:
    #   python plugin_config.py ../plugins construction_safety .. [model_override]
    import sys
    from ultralytics import YOLO

    plugins_dir, plugin_id = sys.argv[1], sys.argv[2]
    models_dir = sys.argv[3] if len(sys.argv) > 3 else "."
    plugin = load_plugin(plugins_dir, plugin_id)
    model_override = sys.argv[4] if len(sys.argv) > 4 else None
    try:
        model = YOLO(model_path_for(plugin, models_dir, model_override))
        cfg = build_config(plugin, model.names, models_dir, model_override)
    except PluginError as e:
        sys.exit(f"INVALID: {e}")
    for w in cfg.warnings:
        print("WARNING:", w)
    print(f"OK: model={cfg.model_path} imgsz={cfg.imgsz} thresholds={cfg.thresholds} class_ids={cfg.class_ids}")
