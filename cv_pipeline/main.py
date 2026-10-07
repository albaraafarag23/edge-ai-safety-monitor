import os
import json
import time
from datetime import datetime, timezone

import cv2
import numpy as np
import redis

from media import MediaRecorder
from plugin_config import DetectionConfig, PluginError, build_config, load_plugin, model_path_for

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PLUGINS_DIR = os.getenv("PLUGINS_DIR", "../plugins")
MODELS_DIR = os.getenv("MODELS_DIR", "..")
# Optional: use a different model file than the plugin names (e.g. a TensorRT .engine on the Jetson)
MODEL_OVERRIDE = os.getenv("MODEL_PATH") or None
SOURCE = os.getenv("SOURCE", "0")
CAMERA_ID = os.getenv("CAMERA_ID", "cam_01")
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


def publish(r: redis.Redis, message: dict):
    # one stream entry per frame; the whole message is JSON in the "data" field
    r.xadd(STREAM_KEY, {"data": json.dumps(message)}, maxlen=1000)


def synthetic_frame(frame_id: int):
    """Plain test image so test mode also produces snapshots and clips."""
    w, h = SYNTHETIC_FRAME_SIZE
    img = np.full((h, w, 3), 60, np.uint8)
    cv2.putText(img, "SYNTHETIC TEST FRAME", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(img, f"{CAMERA_ID}  frame {frame_id}  {utc_now()}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1)
    return img


def log_config(cfg: DetectionConfig):
    for w in cfg.warnings:
        print(f"[CV] WARNING: {w}", flush=True)
    print(f"[CV] Plugin '{cfg.plugin_id}': detecting {cfg.thresholds}", flush=True)


def run_test_mode(r: redis.Redis, plugin: dict, recorder: MediaRecorder):
    # No model in test mode: treat the plugin's own classes as the model's classes
    cfg = build_config(plugin, dict(enumerate(plugin["detection"]["classes"])))
    log_config(cfg)
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

        if new_scene:
            print(f"[CV] Synthetic scene: {[d['class_name'] for d in detections] or 'no detections'}", flush=True)

        time.sleep(1 / SYNTHETIC_FPS)


def run_live_mode(r: redis.Redis, plugin: dict, recorder: MediaRecorder):
    from ultralytics import YOLO

    model = YOLO(model_path_for(plugin, MODELS_DIR, MODEL_OVERRIDE))
    cfg = build_config(plugin, model.names, MODELS_DIR, MODEL_OVERRIDE)
    log_config(cfg)
    source = int(SOURCE) if SOURCE.isdigit() else SOURCE
    print(f"[CV] LIVE MODE — source={source}  model={cfg.model_path}", flush=True)

    model_name = os.path.basename(cfg.model_path)
    for frame_id, result in enumerate(model.predict(
        source=source,
        conf=cfg.min_confidence,
        classes=cfg.class_ids,
        imgsz=cfg.imgsz,
        stream=True,
        show=False,
        save=False,
        verbose=False,
    ), start=1):
        detections = [
            {
                "class_name": model.names[int(b.cls[0])],
                "confidence": round(float(b.conf[0]), 3),
                "bbox": [round(v, 1) for v in b.xyxy[0].tolist()],
            }
            for b in result.boxes
            if cfg.keep(model.names[int(b.cls[0])], float(b.conf[0]))
        ]

        h, w = result.orig_shape
        message = detection_message(frame_id, detections, model_name, (w, h))
        recorder.add(frame_id, result.orig_img, message["detections"])
        publish(r, message)

        if detections:
            print(f"[CV] Detected: {[d['class_name'] for d in detections]}", flush=True)


def main():
    try:
        plugin = load_plugin(PLUGINS_DIR, PLUGIN_ID)
    except PluginError as e:
        raise SystemExit(f"[CV] {e}")

    r = redis.from_url(REDIS_URL, decode_responses=True)
    recorder = MediaRecorder(MEDIA_DIR, REDIS_URL, CAMERA_ID)
    recorder.start()

    try:
        if TEST_MODE:
            run_test_mode(r, plugin, recorder)
        else:
            run_live_mode(r, plugin, recorder)
    except PluginError as e:
        raise SystemExit(f"[CV] Invalid plugin: {e}")


if __name__ == "__main__":
    main()
