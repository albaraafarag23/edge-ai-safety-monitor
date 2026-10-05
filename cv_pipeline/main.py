import os
import json
import uuid
import time
import random
from datetime import datetime, timezone

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
MODEL_PATH = os.getenv("MODEL_PATH", "yolo11n.pt")
SOURCE = os.getenv("SOURCE", "0")
CONFIDENCE = float(os.getenv("CONFIDENCE", "0.4"))
CAMERA_ID = os.getenv("CAMERA_ID", "cam_01")
PLUGIN_ID = os.getenv("PLUGIN_ID", "factory_safety")
STREAM_KEY = "detections"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# Synthetic detections for test mode — simulates what YOLO would produce
SYNTHETIC_SCENARIOS = [
    [{"class": "person", "confidence": 0.91, "bbox": [120.0, 80.0, 400.0, 479.0]}],
    [{"class": "person", "confidence": 0.85, "bbox": [60.0, 100.0, 320.0, 460.0]},
     {"class": "person", "confidence": 0.78, "bbox": [350.0, 90.0, 580.0, 450.0]}],
    [],  # empty frame — no detections
    [{"class": "person", "confidence": 0.93, "bbox": [200.0, 50.0, 500.0, 479.0]}],
    [],
]


def run_test_mode(r: redis.Redis):
    print(f"[CV] TEST MODE — generating synthetic detections every 2s", flush=True)
    scenario_index = 0

    while True:
        objects = SYNTHETIC_SCENARIOS[scenario_index % len(SYNTHETIC_SCENARIOS)]
        scenario_index += 1

        event = {
            "detection_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera_id": CAMERA_ID,
            "plugin_id": PLUGIN_ID,
            "model": "synthetic",
            "objects": json.dumps(objects),
        }

        r.xadd(STREAM_KEY, event, maxlen=1000)

        if objects:
            classes = [o["class"] for o in objects]
            print(f"[CV] Synthetic detection: {classes}", flush=True)
        else:
            print("[CV] Synthetic frame: no detections", flush=True)

        time.sleep(2)


def run_live_mode(r: redis.Redis):
    from ultralytics import YOLO

    model = YOLO(MODEL_PATH)
    source = int(SOURCE) if SOURCE.isdigit() else SOURCE
    print(f"[CV] LIVE MODE — source={source}  model={MODEL_PATH}", flush=True)

    for result in model.predict(
        source=source,
        conf=CONFIDENCE,
        stream=True,
        show=False,
        save=False,
        verbose=False,
    ):
        objects = [
            {
                "class": model.names[int(b.cls[0])],
                "confidence": round(float(b.conf[0]), 3),
                "bbox": [round(v, 1) for v in b.xyxy[0].tolist()],
            }
            for b in result.boxes
        ]

        event = {
            "detection_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera_id": CAMERA_ID,
            "plugin_id": PLUGIN_ID,
            "model": os.path.basename(MODEL_PATH),
            "objects": json.dumps(objects),
        }

        r.xadd(STREAM_KEY, event, maxlen=1000)

        if objects:
            print(f"[CV] Detected: {[o['class'] for o in objects]}", flush=True)


def main():
    r = redis.from_url(REDIS_URL, decode_responses=True)

    if TEST_MODE:
        run_test_mode(r)
    else:
        run_live_mode(r)


if __name__ == "__main__":
    main()
