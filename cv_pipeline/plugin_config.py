"""Turns a plugin's "detection" section into the settings the detector runs with.

The plugin decides which models are loaded (the main model, plus optional extra_models such as a
smoking detector that run on the same frames), which classes are kept and the confidence threshold
for each class. Rules are checked against what the models can actually detect, so a rule that could
never fire stops startup.
"""
import json
from dataclasses import dataclass
from pathlib import Path


class PluginError(Exception):
    pass


@dataclass
class ModelConfig:
    model_path: str
    imgsz: int
    class_ids: list[int]             # model class ids passed to YOLO
    thresholds: dict[str, float]     # class_name -> min confidence

    @property
    def min_confidence(self) -> float:
        return min(self.thresholds.values())

    def keep(self, class_name: str, confidence: float) -> bool:
        return confidence >= self.thresholds.get(class_name, 1.1)


@dataclass
class DetectionConfig:
    plugin_id: str
    models: list[ModelConfig]        # main model first, then extra_models
    warnings: list[str]

    @property
    def thresholds(self) -> dict[str, float]:
        return {k: v for m in self.models for k, v in m.thresholds.items()}

    def keep(self, class_name: str, confidence: float) -> bool:
        return confidence >= self.thresholds.get(class_name, 1.1)


def rule_classes(rule: dict) -> set[str]:
    """Every class a rule depends on. Keep in sync with event_engine/rules.py:rule_classes."""
    classes = set(rule.get("subject_classes", [])) | set(rule.get("near_classes", []))
    for item in rule.get("required", []):
        classes |= set(item.get("present_classes", [])) | set(item.get("absent_classes", []))
    return classes


def model_specs(plugin: dict) -> list[dict]:
    """The main model's section, then each of detection.extra_models (same fields: model, imgsz,
    default_confidence, classes)."""
    det = plugin.get("detection") or {}
    return [det, *det.get("extra_models", [])]


def load_plugin(plugins_dir: str, plugin_id: str) -> dict:
    for path in Path(plugins_dir).glob("*.json"):
        with open(path) as f:
            plugin = json.load(f)
        if plugin.get("plugin_id") == plugin_id:
            return plugin
    raise PluginError(f"No plugin with plugin_id '{plugin_id}' in {plugins_dir}")


def build_config(plugin: dict, model_names: list[dict[int, str]], models_dir: str = ".",
                 model_override: str | None = None) -> DetectionConfig:
    """model_names: each model's id -> class name map (YOLO(...).names), in model_specs order.
    A model without names (None) is skipped with a warning, e.g. an optional model not trained yet."""
    pid = plugin.get("plugin_id", "?")
    det = plugin.get("detection")
    if not det or not det.get("classes"):
        raise PluginError(f"[{pid}] plugin has no detection.classes section")

    warnings, models, requested, not_loaded = [], [], set(), set()
    for spec, names, path in zip(model_specs(plugin), model_names, model_paths(plugin, models_dir, model_override)):
        requested |= set(spec.get("classes", {}))
        if names is None:
            not_loaded |= set(spec.get("classes", {}))
            warnings.append(f"[{pid}] model {path} not found, its classes {sorted(spec.get('classes', {}))} "
                            f"will never be detected")
            continue
        default_conf = float(spec.get("default_confidence", 0.4))
        name_to_id = {name: i for i, name in names.items()}
        thresholds = {}
        for name, opts in spec.get("classes", {}).items():
            if name not in name_to_id:
                warnings.append(f"[{pid}] class '{name}' is not in {Path(path).name}, it will never be detected")
                continue
            thresholds[name] = float((opts or {}).get("confidence", default_conf))
        if not thresholds:
            raise PluginError(f"[{pid}] none of the classes listed for {Path(path).name} exist in it "
                              f"(model classes: {sorted(name_to_id)})")
        models.append(ModelConfig(model_path=path, imgsz=int(spec.get("imgsz", det.get("imgsz", 640))),
                                  class_ids=sorted(name_to_id[n] for n in thresholds), thresholds=thresholds))

    if not models or models[0].model_path != model_paths(plugin, models_dir, model_override)[0]:
        raise PluginError(f"[{pid}] the main model is required")
    detectable = {k for m in models for k in m.thresholds}

    for rule in plugin.get("rules", []):
        if not rule.get("enabled", True) or rule.get("planned"):
            continue
        triggers = rule_classes(rule)
        not_requested = triggers - requested
        if not_requested:
            raise PluginError(f"[{pid}] rule '{rule['rule_id']}' uses {sorted(not_requested)} "
                              f"which are missing from detection.classes / extra_models")
        if not triggers & detectable and triggers & not_loaded:
            warnings.append(f"[{pid}] rule '{rule['rule_id']}' can't fire until its model is available")
        elif not triggers & detectable:
            raise PluginError(f"[{pid}] rule '{rule['rule_id']}' can never fire: none of "
                              f"{sorted(triggers)} can be detected by the models")

    return DetectionConfig(plugin_id=pid, models=models, warnings=warnings)


def model_paths(plugin: dict, models_dir: str = ".", model_override: str | None = None) -> list[str]:
    """Paths of the main model (or model_override, e.g. a TensorRT .engine) and the extra models."""
    specs = model_specs(plugin)
    paths = [str(Path(models_dir) / spec.get("model", "yolo11n.pt")) for spec in specs]
    if model_override:
        paths[0] = model_override
    return paths


def check_main_model(plugin: dict, models_dir: str = ".", model_override: str | None = None):
    """The main model must exist before the detector starts; extra models are optional."""
    path = model_paths(plugin, models_dir, model_override)[0]
    if not Path(path).exists():
        raise PluginError(f"[{plugin.get('plugin_id', '?')}] model file not found: {path} "
                          f"(train it first, or set MODEL_PATH to use another model)")


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
        check_main_model(plugin, models_dir, model_override)
        names = [YOLO(p).names if Path(p).exists() else None for p in model_paths(plugin, models_dir, model_override)]
        cfg = build_config(plugin, names, models_dir, model_override)
    except PluginError as e:
        sys.exit(f"INVALID: {e}")
    for w in cfg.warnings:
        print("WARNING:", w)
    for m in cfg.models:
        print(f"OK: model={m.model_path} imgsz={m.imgsz} thresholds={m.thresholds} class_ids={m.class_ids}")
