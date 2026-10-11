import os
import json
import time
from datetime import datetime, timezone

import cv2
import numpy as np
import redis

from camera import Camera
from live_view import LiveView
from media import MediaRecorder
from plugin_config import (DetectionConfig, PluginError, build_config, check_main_model, load_plugin,
                           model_paths, model_specs)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "../plugins")
MODELS_DIR = os.getenv("MODELS_DIR", "../models")
# Optional: use a different main model file than the plugin names
MODEL_OVERRIDE = os.getenv("MODEL_PATH") or None
# "engine" on the Jetson: use each model's TensorRT build (construction_ppe.engine) when it exists
USE_ENGINE = os.getenv("MODEL_FORMAT", "pt").lower() == "engine"
SOURCE = os.getenv("SOURCE", "0")
CAMERA_SIZE = os.getenv("CAMERA_SIZE", "1920x1080")
CAMERA_DECODE = os.getenv("CAMERA_DECODE", "half")   # see camera.py
CAMERA_CONTROLS = os.getenv("CAMERA_CONTROLS", "power_line_frequency=1")   # 50 Hz mains
CAMERA_ID = os.getenv("CAMERA_ID", "cam_01")
CAMERA_LOCATION = os.getenv("CAMERA_LOCATION") or None  # shown in the dashboard, e.g. "North gate"
PLUGIN_ID = os.getenv("PLUGIN_ID", "construction_safety")
STREAM_KEY = "detections"
MEDIA_DIR = os.getenv("MEDIA_DIR", "../media")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

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
     {"class_name": "cigarette", "confidence": 0.77, "bbox": [382.0, 196.0, 398.0, 203.0]}],  # smoking
    [],  # empty frame — no detections
]


SYNTHETIC_FRAME_SIZE = [640, 480]
SYNTHETIC_FPS = 2
SCENARIO_SECONDS = 5  # long enough for rules with min_duration_s (PPE needs 3 s)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def detection_message(frame_id: int, detections: list[dict], model_name: str, frame_size) -> dict:
    """Detection output, as defined in docs/contracts.md."""
    return {
        "timestamp": utc_now(),
        "camera_id": CAMERA_ID,
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
        r.xadd(STREAM_KEY, {"data": json.dumps(message)}, maxlen=1000)
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


def synthetic_frame(frame_id: int):
    """Plain test image so test mode also produces snapshots and clips."""
    w, h = SYNTHETIC_FRAME_SIZE
    img = np.full((h, w, 3), 60, np.uint8)
    # bottom-left, so it doesn't sit under the dashboard's live-view overlay at the top
    cv2.putText(img, "SYNTHETIC TEST FRAME", (20, h - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(img, f"{CAMERA_ID}  frame {frame_id}  {utc_now()}", (20, h - 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1)
    return img


def log_config(cfg: DetectionConfig):
    for w in cfg.warnings:
        print(f"[CV] WARNING: {w}", flush=True)
    for m in cfg.models:
        print(f"[CV] Plugin '{cfg.plugin_id}': {os.path.basename(m.model_path)} detects {m.thresholds}", flush=True)


def run_test_mode(r: redis.Redis, plugin: dict, recorder: MediaRecorder, live: LiveView):
    # No model in test mode: treat the plugin's own classes as the models' classes
    cfg = build_config(plugin, [dict(enumerate(spec.get("classes", {}))) for spec in model_specs(plugin)])
    log_config(cfg)
    live.set_model("synthetic")
    print(f"[CV] TEST MODE — synthetic detections at {SYNTHETIC_FPS} fps, "
          f"each scene held for {SCENARIO_SECONDS} s", flush=True)
    frame_id = 0

    while True:
        scene = frame_id // (SYNTHETIC_FPS * SCENARIO_SECONDS)
        detections = [o for o in SYNTHETIC_SCENARIOS[scene % len(SYNTHETIC_SCENARIOS)]
                      if cfg.keep(o["class_name"], o["confidence"])]
        new_scene = frame_id % (SYNTHETIC_FPS * SCENARIO_SECONDS) == 0
        frame_id += 1
        message = detection_message(frame_id, detections, "synthetic", SYNTHETIC_FRAME_SIZE)
        recorder.add(frame_id, synthetic_frame(frame_id), message["detections"])
        publish(r, message)
        live.frame_processed()

        if new_scene:
            print(f"[CV] Synthetic scene: {[d['class_name'] for d in detections] or 'no detections'}", flush=True)

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


def run_live_mode(r: redis.Redis, plugin: dict, recorder: MediaRecorder, live: LiveView):
    from ultralytics import YOLO

    check_main_model(plugin, MODELS_DIR, MODEL_OVERRIDE, USE_ENGINE)
    paths = model_paths(plugin, MODELS_DIR, MODEL_OVERRIDE, USE_ENGINE)
    loaded = {p: YOLO(p, task="detect") for p in paths if os.path.exists(p)}   # extra models are optional
    cfg = build_config(plugin, [loaded[p].names if p in loaded else None for p in paths], MODELS_DIR,
                       MODEL_OVERRIDE, USE_ENGINE)
    log_config(cfg)
    camera = Camera(SOURCE, CAMERA_SIZE, decode=CAMERA_DECODE, controls=CAMERA_CONTROLS)
    print(f"[CV] LIVE MODE — source={SOURCE}  models={[m.model_path for m in cfg.models]}", flush=True)

    # e.g. "construction_ppe.engine+smoking.engine" when an extra model runs too
    model_name = "+".join(os.path.basename(m.model_path) for m in cfg.models)
    live.set_model(model_name)
    last = {}   # model path -> its latest detections, reused on frames it skips (every_n_frames)
    for frame_id, frame in enumerate(camera.frames(), start=1):
        detections = []
        for m in cfg.models:   # main model, then each extra model (e.g. smoking) on the same frame
            if (frame_id - 1) % m.every_n_frames == 0:
                model = loaded[m.model_path]
                boxes = model.predict(frame, conf=m.min_confidence, classes=m.class_ids, imgsz=m.imgsz,
                                      verbose=False)[0].boxes
                last[m.model_path] = detect(model, m, boxes, camera.scale)
            detections += last[m.model_path]

        message = detection_message(frame_id, detections, model_name, camera.frame_size)
        recorder.add(frame_id, frame, message["detections"], 1 / camera.scale)
        publish(r, message)
        live.frame_processed()

        if detections:
            print(f"[CV] Detected: {[d['class_name'] for d in detections]}", flush=True)


def main():
    try:
        plugin = load_plugin(PLUGINS_DIR, PLUGIN_ID)
    except PluginError as e:
        raise SystemExit(f"[CV] {e}")

    r = redis.from_url(REDIS_URL, decode_responses=True)
    live = LiveView(REDIS_URL, CAMERA_ID, PLUGIN_ID, "test" if TEST_MODE else "live", CAMERA_LOCATION)
    recorder = MediaRecorder(MEDIA_DIR, REDIS_URL, CAMERA_ID, live_view=live)
    recorder.start()

    try:
        if TEST_MODE:
            run_test_mode(r, plugin, recorder, live)
        else:
            run_live_mode(r, plugin, recorder, live)
    except PluginError as e:
        raise SystemExit(f"[CV] Invalid plugin: {e}")


if __name__ == "__main__":
    main()
