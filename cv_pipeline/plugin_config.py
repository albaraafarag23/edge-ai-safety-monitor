"""Turns a plugin's "detection" section into the settings the detector runs with.

The plugin decides which models are loaded (the main model, plus optional extra_models such as a
smoking detector that run on the same frames), which classes are kept and the confidence threshold
for each class. Rules are checked against what the models can actually detect, so a rule that could
never fire stops startup.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path


class PluginError(Exception):
    pass


@dataclass
class ModelConfig:
    model_path: str
    imgsz: int | list[int]           # a TensorRT build's own input size [height, width] when it has one
    class_ids: list[int]             # model class ids passed to YOLO
    thresholds: dict[str, float]     # class_name -> min confidence
    every_n_frames: int = 1          # run on every n-th frame only, reuse the last result in between
    crop_from: str | None = None     # classifier: runs on a crop of each box of this class (e.g. Person)
    crop: int = 384                  # crop size the classifier was trained on
    # class_name -> widest believable box, as a fraction of the frame width (e.g. Person 0.6: a dark, grainy
    # empty room once came back as one frame-wide "Person" at 0.8 confidence)
    max_width: dict[str, float] = field(default_factory=dict)
    # pose model (e.g. yolo11n-pose.pt, "pose": true): its people become postures (posture.py), e.g. "lying"
    pose: bool = False
    # "still": true: each box also says how long it has stayed put (attributes.still_s), e.g. a person down
    still: bool = False
    # fall detector ("fall": {...}): its boxes are checked by a lying classifier and judged over time
    # (falls.py); it reports one class (e.g. "lying") with attributes fell / down_s / still_s
    fall: "FallSpec | None" = None
    # classes used only inside the detector ("internal": true, e.g. yolo11n's "person" for falls.py): never
    # published, so they are not drawn on the picture or seen by the rules
    internal: set = field(default_factory=set)

    @property
    def min_confidence(self) -> float:
        return min(self.thresholds.values())

    def keep(self, class_name: str, confidence: float, width_fraction: float = 0.0) -> bool:
        return (confidence >= self.thresholds.get(class_name, 1.1)
                and width_fraction <= self.max_width.get(class_name, 1.0))


@dataclass
class FallSpec:
    """The "fall" section of an extra model: {"detects": the detector's class (e.g. "person_down"),
    "verifier": classifier file (e.g. lying_verify.pt), "verified_class": its "yes" class (default "lying"),
    "verify_at": P(yes) a box needs (default 0.8), "verifier_imgsz" (default 224),
    "upright_class": the main model's person class whose upright boxes show a fall happening (default "Person")}."""
    detects: str
    verifier_path: str
    verified_class: str = "lying"
    verify_at: float = 0.8
    verifier_imgsz: int = 224
    upright_class: str = "Person"


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


POSTURES = {"lying"}   # what a pose model can report (posture.py)


def rule_classes(rule: dict) -> set[str]:
    """Every class a rule depends on. Keep in sync with event_engine/rules.py:rule_classes."""
    classes = set(rule.get("subject_classes", [])) | set(rule.get("near_classes", []))
    for item in rule.get("required", []):
        classes |= set(item.get("present_classes", [])) | set(item.get("absent_classes", []))
    return classes


def model_specs(plugin: dict) -> list[dict]:
    """The main model's section, then each of detection.extra_models (same fields: model, imgsz,
    default_confidence, classes, plus optional every_n_frames; a classifier also has crop_from and crop)."""
    det = plugin.get("detection") or {}
    return [det, *det.get("extra_models", [])]


def test_mode_names(plugin: dict) -> list[dict[int, str]]:
    """Test mode loads no models: each one "has" the classes the plugin asks of it (a pose model: person)."""
    return [{0: "person"} if spec.get("pose") else {0: spec["fall"]["detects"]} if spec.get("fall")
            else dict(enumerate(spec.get("classes", {}))) for spec in model_specs(plugin)]


def verifier_path(spec: dict, models_dir: str = ".", engine: bool = False) -> str | None:
    """The lying check of a fall detector (its TensorRT build on the Jetson when there is one), or None."""
    name = (spec.get("fall") or {}).get("verifier")
    if not name:
        return None
    path = Path(models_dir) / name
    return str(path.with_suffix(".engine")) if engine and path.with_suffix(".engine").exists() else str(path)


def load_plugin(plugins_dir: str, plugin_id: str) -> dict:
    for path in Path(plugins_dir).glob("*.json"):
        with open(path) as f:
            plugin = json.load(f)
        if plugin.get("plugin_id") == plugin_id:
            return plugin
    raise PluginError(f"No plugin with plugin_id '{plugin_id}' in {plugins_dir}")


def build_config(plugin: dict, model_names: list[dict[int, str]], models_dir: str = ".",
                 model_override: str | None = None, engine: bool = False) -> DetectionConfig:
    """model_names: each model's id -> class name map (YOLO(...).names), in model_specs order.
    A model without names (None) is skipped with a warning, e.g. an optional model not trained yet."""
    pid = plugin.get("plugin_id", "?")
    det = plugin.get("detection")
    if not det or not det.get("classes"):
        raise PluginError(f"[{pid}] plugin has no detection.classes section")

    warnings, models, requested, not_loaded = [], [], set(), set()
    for spec, names, path in zip(model_specs(plugin), model_names, model_paths(plugin, models_dir, model_override, engine)):
        requested |= set(spec.get("classes", {}))
        if names is None:
            not_loaded |= set(spec.get("classes", {}))
            warnings.append(f"[{pid}] model {path} not found, its classes {sorted(spec.get('classes', {}))} "
                            f"will never be detected")
            continue
        default_conf = float(spec.get("default_confidence", 0.4))
        name_to_id = {name: i for i, name in names.items()}
        thresholds, max_width = {}, {}
        internal = {n for n, o in spec.get("classes", {}).items() if (o or {}).get("internal")}
        pose = bool(spec.get("pose"))
        fall = spec.get("fall")
        if fall:
            # like a pose model: the classes are what it reports (e.g. "lying"), not the detector's own class
            if pose or spec.get("crop_from"):
                raise PluginError(f"[{pid}] {Path(path).name}: a fall detector can't also be a pose model or crop classifier")
            if len(spec.get("classes", {})) != 1:
                raise PluginError(f"[{pid}] fall detector {Path(path).name}: list exactly one class, the one it reports")
            if fall.get("detects") not in name_to_id:
                raise PluginError(f"[{pid}] fall detector {Path(path).name} has no class '{fall.get('detects')}' "
                                  f"(its classes: {sorted(name_to_id)})")
            if not fall.get("verifier"):
                raise PluginError(f"[{pid}] fall detector {Path(path).name}: \"fall\" needs a \"verifier\" model")
        if pose:
            # the classes are postures worked out from the keypoints, not the model's own class ("person")
            unknown = set(spec.get("classes", {})) - POSTURES
            if unknown:
                raise PluginError(f"[{pid}] pose model {Path(path).name}: unknown posture(s) {sorted(unknown)} "
                                  f"(known: {sorted(POSTURES)})")
            if "person" not in name_to_id:
                raise PluginError(f"[{pid}] pose model {Path(path).name} has no 'person' class")
        for name, opts in spec.get("classes", {}).items():
            if pose or fall:
                thresholds[name] = float((opts or {}).get("confidence", default_conf))
                continue
            if name not in name_to_id:
                warnings.append(f"[{pid}] class '{name}' is not in {Path(path).name}, it will never be detected")
                continue
            thresholds[name] = float((opts or {}).get("confidence", default_conf))
            if (opts or {}).get("max_width") is not None:
                limit = float(opts["max_width"])
                if not 0 < limit <= 1:
                    raise PluginError(f"[{pid}] class '{name}': max_width must be a fraction of the frame width (0-1)")
                max_width[name] = limit
        if not thresholds:
            raise PluginError(f"[{pid}] none of the classes listed for {Path(path).name} exist in it "
                              f"(model classes: {sorted(name_to_id)})")
        models.append(ModelConfig(model_path=path,
                                  imgsz=engine_imgsz(path) or int(spec.get("imgsz", det.get("imgsz", 640))),
                                  class_ids=[name_to_id["person"]] if pose else [name_to_id[fall["detects"]]] if fall
                                  else sorted(name_to_id[n] for n in thresholds),
                                  thresholds=thresholds, pose=pose, still=bool(spec.get("still")),
                                  every_n_frames=max(1, int(spec.get("every_n_frames", 1))),
                                  crop_from=spec.get("crop_from"), crop=int(spec.get("crop", 384)),
                                  max_width=max_width, internal=internal,
                                  fall=FallSpec(detects=fall["detects"],
                                                verifier_path=verifier_path(spec, models_dir, engine),
                                                verified_class=fall.get("verified_class", "lying"),
                                                verify_at=float(fall.get("verify_at", 0.8)),
                                                verifier_imgsz=int(fall.get("verifier_imgsz", 224)),
                                                upright_class=fall.get("upright_class", "Person")) if fall else None))

    if not models or models[0].model_path != model_paths(plugin, models_dir, model_override, engine)[0]:
        raise PluginError(f"[{pid}] the main model is required")
    for m in models[1:]:
        if m.fall and not any(m.fall.upright_class in o.thresholds for o in models if o is not m):
            warnings.append(f"[{pid}] {Path(m.model_path).name}: no model detects '{m.fall.upright_class}', "
                            f"so no fall is ever seen happening (only people found already lying)")
        if m.crop_from and m.crop_from not in models[0].thresholds:
            raise PluginError(f"[{pid}] {Path(m.model_path).name} crops '{m.crop_from}' boxes, "
                              f"but the main model doesn't detect '{m.crop_from}'")
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


def model_paths(plugin: dict, models_dir: str = ".", model_override: str | None = None,
                engine: bool = False) -> list[str]:
    """Paths of the main model (or model_override) and the extra models. With engine=True (Jetson), each
    model's TensorRT build next to it (smoking.pt -> smoking.engine) is used when it exists."""
    specs = model_specs(plugin)
    paths = [str(Path(models_dir) / spec.get("model", "yolo11n.pt")) for spec in specs]
    if engine:
        paths = [str(Path(p).with_suffix(".engine")) if Path(p).with_suffix(".engine").exists() else p
                 for p in paths]
    if model_override:
        paths[0] = model_override
    return paths


def check_main_model(plugin: dict, models_dir: str = ".", model_override: str | None = None,
                     engine: bool = False):
    """The main model must exist before the detector starts; extra models are optional."""
    path = model_paths(plugin, models_dir, model_override, engine)[0]
    if not Path(path).exists():
        raise PluginError(f"[{plugin.get('plugin_id', '?')}] model file not found: {path} "
                          f"(train it first, or set MODEL_PATH to use another model)")

def engine_imgsz(path: str) -> list[int] | None:
    """The input size [height, width] an Ultralytics TensorRT build was made for, from the metadata at the start
    of the .engine file (4-byte length + JSON). A build for the camera's own shape (e.g. 544x960 for 960x540
    frames) skips the grey padding a square 960x960 one needs, which is almost half its work. None otherwise."""
    if not str(path).endswith(".engine"):
        return None
    try:
        with open(path, "rb") as f:
            n = int.from_bytes(f.read(4), "little")
            if not 0 < n < 1_000_000:
                return None
            size = json.loads(f.read(n)).get("imgsz")
    except (OSError, ValueError):
        return None
    if isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size):
        return size
    return None

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
