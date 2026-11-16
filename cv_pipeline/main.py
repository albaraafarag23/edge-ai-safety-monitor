"""The detector: reads the cameras, runs the plugin's models on each frame and publishes what it sees.

One process serves every camera: the models are loaded once and take the cameras' newest frames in turn,
so a second camera costs frame rate, not memory. Each camera has its own reader thread (camera.py), frame
buffer for snapshots and clips (media.py), live view (live_view.py) and person tracker (tracker.py).
Cameras come from CAMERAS_FILE (a JSON list, config/cameras.example.json); without that file there is one
camera, set by SOURCE / CAMERA_ID / CAMERA_LOCATION as before.
"""
import os
import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np
import redis

import plugin_source
from camera import Camera
from faces import FaceIdentifier
from live_view import LiveView
from media import MediaListener, MediaRecorder
from person_crops import cut, upper_body_box
from plugin_config import (DetectionConfig, PluginError, build_config, check_main_model, load_plugin,
                           model_paths, model_specs)
from tracker import Tracker

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "../plugins")
MODELS_DIR = os.getenv("MODELS_DIR", "../models")
# Optional: use a different main model file than the plugin names
MODEL_OVERRIDE = os.getenv("MODEL_PATH") or None
# "engine" on the Jetson: use each model's TensorRT build (construction_ppe.engine) when it exists
USE_ENGINE = os.getenv("MODEL_FORMAT", "pt").lower() == "engine"
# several cameras: a JSON list, see config/cameras.example.json. Without the file, the one camera below.
CAMERAS_FILE = os.getenv("CAMERAS_FILE", "/config/cameras.json")
SOURCE = os.getenv("SOURCE", "0")
CAMERA_SIZE = os.getenv("CAMERA_SIZE", "1920x1080")
CAMERA_DECODE = os.getenv("CAMERA_DECODE", "half")   # see camera.py
CAMERA_CONTROLS = os.getenv("CAMERA_CONTROLS") or "power_line_frequency=1"
# Frames a second asked of a USB camera. A sharp 1080p picture is a large JPEG, and in the 30 mode this camera
# sends nearly half of them cut off (17 good ones a second on the Jetson); its 60 mode gets ~40 through, at the
# price of a darker picture in dim light (jetson/README.md).
CAMERA_FPS = int(os.getenv("CAMERA_FPS") or 30)   # 50 Hz mains
CAMERA_ID = os.getenv("CAMERA_ID", "cam_01")
CAMERA_LOCATION = os.getenv("CAMERA_LOCATION") or None  # shown in the dashboard, e.g. "North gate"
PLUGIN_ID = plugin_source.FIXED_ID   # main() replaces it with the live plugin (a rule drive's, or the base one)
STREAM_KEY = "detections"
# detections waiting for the rule engine; older ones are dropped (about a minute at 30 frames a second in all)
STREAM_MAXLEN = 2000
MEDIA_DIR = os.getenv("MEDIA_DIR", "../media")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
CAMERA_ID_FORMAT = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
LOG_EVERY_S = 10.0

# Synthetic detections for test mode — simulates what the construction PPE model would produce
_WORKER = {"class_name": "Person", "confidence": 0.91, "bbox": [300.0, 120.0, 400.0, 400.0]}
SYNTHETIC_SCENARIOS = [
    [_WORKER,
     {"class_name": "Hardhat", "confidence": 0.88, "bbox": [325.0, 120.0, 375.0, 160.0]},
     {"class_name": "Safety Vest", "confidence": 0.84, "bbox": [310.0, 180.0, 390.0, 280.0]}],
    [_WORKER,
     {"class_name": "NO-Hardhat", "confidence": 0.82, "bbox": [325.0, 120.0, 375.0, 160.0]},
     {"class_name": "Safety Vest", "confidence": 0.84, "bbox": [310.0, 180.0, 390.0, 280.0]}],
    [_WORKER,
     {"class_name": "machinery", "confidence": 0.86, "bbox": [420.0, 150.0, 620.0, 400.0]}],
    [{"class_name": "Person", "confidence": 0.89, "bbox": [60.0, 200.0, 140.0, 420.0]}],  # in excavation zone
    [_WORKER, {"class_name": "Hardhat", "confidence": 0.88, "bbox": [325.0, 120.0, 375.0, 160.0]},
     {"class_name": "Safety Vest", "confidence": 0.84, "bbox": [310.0, 180.0, 390.0, 280.0]},
     {"class_name": "smoking", "confidence": 0.93, "bbox": [278.0, 98.0, 422.0, 242.0]}],  # head and upper body
    [],  # empty frame — no detections
]


SYNTHETIC_FRAME_SIZE = [640, 480]
SYNTHETIC_FPS = 2
SCENARIO_SECONDS = 5  # long enough for rules with min_duration_s (PPE needs 3 s)

# Person classifiers (crop_from): people shorter than this in the frame the model sees are skipped (same
# limit as the training crops), and at most this many people per frame are classified, tallest first.
MIN_PERSON_PX = 48
MAX_PEOPLE = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def camera_settings() -> list[dict]:
    """The cameras to run: [{"id", "source", "location", "size", "decode", "controls"}, ...]."""
    default = {"id": CAMERA_ID, "source": SOURCE, "location": CAMERA_LOCATION, "size": CAMERA_SIZE,
               "decode": CAMERA_DECODE, "controls": CAMERA_CONTROLS, "fps": CAMERA_FPS}
    if not os.path.isfile(CAMERAS_FILE):
        cameras = [default]
    else:
        try:
            with open(CAMERAS_FILE) as f:
                entries = json.load(f)
        except (OSError, ValueError) as e:
            raise SystemExit(f"[CV] {CAMERAS_FILE} can't be read: {e}")
        if not isinstance(entries, list) or not all(isinstance(c, dict) for c in entries):
            raise SystemExit(f"[CV] {CAMERAS_FILE} must be a list of cameras, see config/cameras.example.json")
        cameras = [{**default, "location": None, **c} for c in entries if c.get("enabled", True)]
        missing = [c.get("id") for c in entries if c.get("enabled", True) and "source" not in c]
        if missing and not TEST_MODE:
            raise SystemExit(f"[CV] {CAMERAS_FILE}: no \"source\" for camera(s) {missing}")
    ids = [str(c.get("id", "")) for c in cameras]
    bad = [i for i in ids if not CAMERA_ID_FORMAT.match(i)]
    if not cameras or bad or len(set(ids)) != len(ids):
        raise SystemExit(f"[CV] Camera ids must be unique, 1-40 letters, digits, - or _ (got {ids})")
    return cameras


def detection_message(camera_id: str, frame_id: int, detections: list[dict], model_name: str, frame_size) -> dict:
    """Detection output, as defined in docs/contracts.md."""
    return {
        "timestamp": utc_now(),
        "camera_id": camera_id,
        "frame_id": frame_id,
        "plugin_id": PLUGIN_ID,
        "model": model_name,
        "frame_size": list(frame_size),
        "detections": [
            {"detection_id": f"det_{i:03d}", "class_name": d["class_name"], "confidence": d["confidence"],
             "bbox": d["bbox"], "attributes": d.get("attributes", {})}
            for i, d in enumerate(detections, 1)
        ],
    }


_redis_down_since: float | None = None


def publish(r: redis.Redis, message: dict):
    # one stream entry per frame; the whole message is JSON in the "data" field
    global _redis_down_since
    try:
        r.xadd(STREAM_KEY, {"data": json.dumps(message)}, maxlen=STREAM_MAXLEN, approximate=True)
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
        # A Redis restart must not stop detection (reopening the camera and loading the models takes
        # a while on the Jetson). Detections are live data, so the ones made meanwhile are dropped;
        # redis-py reconnects on the next frame.
        if _redis_down_since is None:
            _redis_down_since = time.monotonic()
            print(f"[CV] Redis unreachable ({e}); detection continues, results dropped until it is back", flush=True)
        return
    if _redis_down_since is not None:
        print(f"[CV] Redis is back after {time.monotonic() - _redis_down_since:.0f} s", flush=True)
        _redis_down_since = None


def synthetic_frame(camera_id: str, frame_id: int):
    """Plain test image so test mode also produces snapshots and clips."""
    w, h = SYNTHETIC_FRAME_SIZE
    img = np.full((h, w, 3), 60, np.uint8)
    # bottom-left, so it doesn't sit under the dashboard's live-view overlay at the top
    cv2.putText(img, "SYNTHETIC TEST FRAME", (20, h - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(img, f"{camera_id}  frame {frame_id}  {utc_now()}", (20, h - 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1)
    return img


def log_config(cfg: DetectionConfig):
    for w in cfg.warnings:
        print(f"[CV] WARNING: {w}", flush=True)
    for m in cfg.models:
        print(f"[CV] Plugin '{cfg.plugin_id}': {os.path.basename(m.model_path)} detects {m.thresholds}", flush=True)


@dataclass
class Unit:
    """One camera and everything that belongs to it."""
    camera_id: str
    live: LiveView
    recorder: MediaRecorder
    camera: Camera | None = None        # None in test mode
    tracker: Tracker = field(default_factory=Tracker)
    frame_id: int = 0
    seen: int = 0                       # the camera's frame counter at the last frame processed
    last: dict = field(default_factory=dict)   # model path -> its latest detections, reused on frames it skips
    logged: tuple = (0.0, None)         # when and what was last logged


def log_detections(unit: Unit, detections: list[dict]):
    """What a camera sees, logged when it changes and at most every LOG_EVERY_S (not once per frame)."""
    seen = tuple(sorted({(d.get("attributes") or {}).get("person_name") or d["class_name"] for d in detections}))
    now = time.monotonic()
    if seen != unit.logged[1] and now - unit.logged[0] >= 1 or (seen and now - unit.logged[0] >= LOG_EVERY_S):
        unit.logged = (now, seen)
        print(f"[CV] {unit.camera_id}: {', '.join(seen) or 'nothing'}", flush=True)


def run_test_mode(r: redis.Redis, plugin: dict, units: list[Unit]):
    # No model in test mode: treat the plugin's own classes as the models' classes
    cfg = build_config(plugin, [dict(enumerate(spec.get("classes", {}))) for spec in model_specs(plugin)])
    log_config(cfg)
    for unit in units:
        unit.live.set_model("synthetic")
        unit.live.set_frame_size(*SYNTHETIC_FRAME_SIZE)
    print(f"[CV] TEST MODE — synthetic detections at {SYNTHETIC_FPS} fps on {[u.camera_id for u in units]}, "
          f"each scene held for {SCENARIO_SECONDS} s", flush=True)
    per_scene = SYNTHETIC_FPS * SCENARIO_SECONDS

    while True:
        for n, unit in enumerate(units):
            # each camera starts at a different scene, so they don't all show the same thing
            scene = unit.frame_id // per_scene + n * 2
            detections = [o for o in SYNTHETIC_SCENARIOS[scene % len(SYNTHETIC_SCENARIOS)]
                          if cfg.keep(o["class_name"], o["confidence"])]
            unit.frame_id += 1
            message = detection_message(unit.camera_id, unit.frame_id, detections, "synthetic", SYNTHETIC_FRAME_SIZE)
            unit.recorder.add(unit.frame_id, synthetic_frame(unit.camera_id, unit.frame_id), message["detections"])
            publish(r, message)
            unit.live.frame_processed()
            log_detections(unit, detections)
        time.sleep(1 / SYNTHETIC_FPS)


def detect(model, cfg_model, boxes, scale: float = 1.0) -> list[dict]:
    """scale maps boxes from the frame the model saw back to camera pixels (see camera.py)."""
    return [
        {
            "class_name": model.names[int(b.cls[0])],
            "confidence": round(float(b.conf[0]), 3),
            "bbox": [round(v * scale, 1) for v in b.xyxy[0].tolist()],
        }
        for b in boxes
        if cfg_model.keep(model.names[int(b.cls[0])], float(b.conf[0]))
    ]


def classify_people(model, cfg_model, frame, detections: list[dict], scale: float = 1.0) -> list[dict]:
    """Classifier with crop_from (e.g. the smoking-act model): classify each person's head and upper body,
    and report that region as a box of each class over its threshold (e.g. "smoking")."""
    h, w = frame.shape[:2]
    # the person's attributes (who they are) go onto what is found on them, e.g. the "smoking" box
    people = [([v / scale for v in d["bbox"]], d.get("attributes") or {})
              for d in detections if d["class_name"] == cfg_model.crop_from]
    people = [p for p in people if p[0][3] - p[0][1] >= MIN_PERSON_PX]
    found = []
    for box, attributes in sorted(people, key=lambda p: p[0][3] - p[0][1], reverse=True)[:MAX_PEOPLE]:
        region = upper_body_box(box, w, h)
        # one crop at a time: the TensorRT build takes a batch of 1
        probs = model.predict(cut(frame, region, cfg_model.crop), imgsz=cfg_model.imgsz,
                              verbose=False)[0].probs.data.tolist()
        x1, y1, x2, y2 = max(region[0], 0), max(region[1], 0), min(region[2], w), min(region[3], h)
        found += [{"class_name": model.names[i], "confidence": round(p, 3),
                   "bbox": [round(v * scale, 1) for v in (x1, y1, x2, y2)], "attributes": dict(attributes)}
                  for i, p in enumerate(probs) if cfg_model.keep(model.names[i], p)]
    return found


def identify_people(faces: FaceIdentifier, unit: Unit, frame, detections: list[dict], subject: str):
    """Follows each person across frames and adds who they are (attributes) once face recognition knows."""
    people = [d for d in detections if d["class_name"] == subject]
    now = time.time()
    ids, gone = unit.tracker.update([d["bbox"] for d in people], now)
    faces.forget(unit.camera_id, gone)
    for d, track_id in zip(people, ids):
        faces.observe(unit.camera_id, track_id, frame, d["bbox"], now)
        d["attributes"] = {"track_id": track_id, **faces.identity(unit.camera_id, track_id)}


class Profile:
    """CV_PROFILE=1: every 10 s, how many frames the cameras delivered and the detector handled, and the average
    milliseconds of each stage per handled frame. Off by default (costs almost nothing either way)."""
    def __init__(self, units: list[Unit]):
        self.on = os.getenv("CV_PROFILE", "") not in ("", "0", "false")
        self.units, self.ms, self.handled = units, {}, 0
        self.start, self.seen = time.monotonic(), {}

    def add(self, stage: str, since: float) -> float:
        now = time.perf_counter()
        if self.on:
            self.ms[stage] = self.ms.get(stage, 0.0) + (now - since) * 1000
        return now

    def speed(self, name: str, speed: dict):
        """Ultralytics' own split of a predict call: preprocess, inference, postprocess (ms)."""
        if self.on:
            for k, v in speed.items():
                key = f"{name}.{k[:3]}"
                self.ms[key] = self.ms.get(key, 0.0) + (v or 0.0)

    def frame(self):
        if not self.on:
            return
        self.handled += 1
        now = time.monotonic()
        if now - self.start < 10:
            return
        dt = now - self.start
        arrived = {u.camera_id: (u.camera.count - self.seen.get(u.camera_id, 0)) / dt for u in self.units}
        self.seen = {u.camera_id: u.camera.count for u in self.units}
        stages = "  ".join(f"{k} {v / self.handled:.1f}" for k, v in self.ms.items())
        stages += "  | waited in camera " + ", ".join(f"{u.camera.wait_ms:.0f}" for u in self.units)
        stages += "  picture age at publish " + ", ".join(f"{u.live.age_ms:.0f}" for u in self.units)
        print(f"[CV] profile: camera {', '.join(f'{k} {v:.1f}' for k, v in arrived.items())} fps, "
              f"handled {self.handled / dt:.1f} fps | ms/frame: {stages}", flush=True)
        self.ms, self.handled, self.start = {}, 0, now


def run_live_mode(r: redis.Redis, plugin: dict, units: list[Unit], settings: list[dict], faces: FaceIdentifier):
    from ultralytics import YOLO

    check_main_model(plugin, MODELS_DIR, MODEL_OVERRIDE, USE_ENGINE)
    paths = model_paths(plugin, MODELS_DIR, MODEL_OVERRIDE, USE_ENGINE)
    loaded = {p: YOLO(p, task="classify" if spec.get("crop_from") else "detect")   # extra models are optional
              for p, spec in zip(paths, model_specs(plugin)) if os.path.exists(p)}
    cfg = build_config(plugin, [loaded[p].names if p in loaded else None for p in paths], MODELS_DIR,
                       MODEL_OVERRIDE, USE_ENGINE)
    log_config(cfg)
    # e.g. "construction_ppe.engine+smoking.engine" when an extra model runs too
    model_name = "+".join(os.path.basename(m.model_path) for m in cfg.models)
    # the people face recognition names: the class person classifiers crop, else the plugin's person class
    subject = next((m.crop_from for m in cfg.models if m.crop_from), None) or next(
        (name for name in cfg.models[0].thresholds if name.lower() == "person"), None)

    new_frame = threading.Event()   # set by any camera: one loop waits on all of them
    for unit, c in zip(units, settings):
        unit.camera = Camera(c["source"], c["size"], fps=int(c.get("fps") or CAMERA_FPS), decode=c["decode"],
                             controls=c["controls"] or "", wake=new_frame)
        unit.live.set_model(model_name)
    print(f"[CV] LIVE MODE — cameras={[(u.camera_id, u.camera.name) for u in units]}  "
          f"models={[m.model_path for m in cfg.models]}", flush=True)

    prof = Profile(units)
    while units:
        new_frame.clear()
        busy = False
        for unit in list(units):
            frame = unit.camera.poll(unit.seen)
            if frame is None:
                if unit.camera.ended:
                    print(f"[CV] {unit.camera_id}: the video has ended", flush=True)
                    units.remove(unit)
                continue
            busy = True
            t = time.perf_counter()
            unit.seen = frame.n
            unit.frame_id += 1
            unit.live.set_frame_size(*unit.camera.frame_size)
            detections = []
            for m in cfg.models:   # main model, then each extra model (e.g. smoking) on the same frame
                if (unit.frame_id - 1) % m.every_n_frames == 0:
                    model = loaded[m.model_path]
                    name = os.path.splitext(os.path.basename(m.model_path))[0]
                    if m.crop_from:   # the main model's people are already in detections
                        unit.last[m.model_path] = classify_people(model, m, frame.image, detections, frame.scale)
                        t = prof.add(name, t)
                    else:
                        result = model.predict(frame.image, conf=m.min_confidence, classes=m.class_ids,
                                               imgsz=m.imgsz, verbose=False)[0]
                        unit.last[m.model_path] = detect(model, m, result.boxes, frame.scale)
                        t = prof.add(name, t)
                        prof.speed(name, result.speed)
                        if m is cfg.models[0] and subject:
                            identify_people(faces, unit, frame, unit.last[m.model_path], subject)
                            t = prof.add("faces", t)
                detections += unit.last.get(m.model_path, [])

            message = detection_message(unit.camera_id, unit.frame_id, detections, model_name, unit.camera.frame_size)
            unit.recorder.add(unit.frame_id, frame.image, message["detections"], 1 / frame.scale, frame.at)
            t = prof.add("recorder", t)
            publish(r, message)
            unit.live.frame_processed()
            log_detections(unit, detections)
            prof.add("publish", t)
            prof.frame()
        if not busy:
            new_frame.wait(timeout=1)


def live_plugin(r) -> str:
    """The plugin to run (plugin_source.py). In drive mode the loader's word in Redis decides; if Redis can't be
    asked right now, the base plugin runs (no rules) and the watcher below corrects it."""
    try:
        return plugin_source.active_id(r.get(plugin_source.STATUS_KEY))
    except redis.exceptions.RedisError:
        return plugin_source.active_id(None)


def follow_plugin(r, running: str):
    """Ends the process when another plugin should run (a rule drive went in or came out): Docker starts the
    detector again, and it loads that plugin and its models. Simple, and nothing of the old plugin stays loaded."""
    def watch():
        while True:
            time.sleep(1)
            try:
                wanted = plugin_source.active_id(r.get(plugin_source.STATUS_KEY))
            except redis.exceptions.RedisError:
                continue   # no word is not a change
            if wanted != running:
                print(f"[CV] The live plugin is now '{wanted}' (was '{running}'): restarting to load it", flush=True)
                os._exit(0)
    if plugin_source.SOURCE == "drive":
        threading.Thread(target=watch, daemon=True, name="plugin-watch").start()


def main():
    global PLUGIN_ID, MODELS_DIR
    r = redis.from_url(REDIS_URL, decode_responses=True)
    PLUGIN_ID = live_plugin(r)
    plugin = plugin_source.load(PLUGIN_ID)
    if plugin is None:
        if plugin_source.from_drive(PLUGIN_ID):   # the drive came out between the loader's word and this read
            print(f"[CV] Plugin '{PLUGIN_ID}' is not in the slot any more, starting again", flush=True)
            time.sleep(2)
            raise SystemExit(0)
        raise SystemExit(f"[CV] Plugin '{PLUGIN_ID}' not found in {plugin_source.PLUGINS_DIR}")
    MODELS_DIR = plugin_source.models_dir(PLUGIN_ID, MODELS_DIR)
    print(f"[CV] Plugin: {plugin.get('name', PLUGIN_ID)} ({PLUGIN_ID})"
          + (" from a rule drive" if plugin_source.from_drive(PLUGIN_ID) else ""), flush=True)
    follow_plugin(r, PLUGIN_ID)
    settings = camera_settings()

    units = []
    for c in settings:
        live = LiveView(REDIS_URL, c["id"], PLUGIN_ID, "test" if TEST_MODE else "live", c.get("location"))
        units.append(Unit(c["id"], live, MediaRecorder(MEDIA_DIR, c["id"], live_view=live)))
    MediaListener(REDIS_URL, {u.camera_id: u.recorder for u in units}, MEDIA_DIR,
                  os.getenv("DETECTOR_ID") or units[0].camera_id).start()
    # in test mode too: the console's People page still learns how each enrolled photo did
    faces = FaceIdentifier(REDIS_URL)
    print(f"[CV] Face recognition: {faces.status}", flush=True)

    try:
        if TEST_MODE:
            run_test_mode(r, plugin, units)
        else:
            run_live_mode(r, plugin, units, settings, faces)
    except PluginError as e:
        raise SystemExit(f"[CV] Invalid plugin: {e}")


if __name__ == "__main__":
    main()
