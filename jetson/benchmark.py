"""Speed and power benchmark on the Jetson: model only, camera only, and camera + model.

Runs inside the Jetson container (see jetson/README.md), which starts tegrastats on the host and
mounts its log at /logs/tegrastats.log so each phase gets its average board power (VDD_IN) and GPU load.
Writes /out/<name>.json.

    python3 benchmark.py /models/construction_ppe.engine --imgsz 960 --name engine_960_maxn
    python3 benchmark.py /models/construction_ppe.engine --imgsz 960 --decode half --name engine_960_half
"""
import argparse
import json
import re
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

TEGRASTATS = Path("/logs/tegrastats.log")


class Power:
    """Average VDD_IN (whole board, mW) and GR3D_FREQ (GPU load, %) from the tegrastats log between start() and stop()."""

    def start(self):
        self.offset = TEGRASTATS.stat().st_size if TEGRASTATS.exists() else None

    def stop(self):
        if self.offset is None:
            return {}
        with TEGRASTATS.open() as f:
            f.seek(self.offset)
            lines = f.read().splitlines()
        watts = [int(m.group(1)) / 1000 for m in map(re.compile(r"VDD_IN (\d+)mW").search, lines) if m]
        gpu = [int(m.group(1)) for m in map(re.compile(r"GR3D_FREQ (\d+)%").search, lines) if m]
        if not watts:
            return {}
        return {"power_w": round(statistics.mean(watts), 2), "power_w_max": round(max(watts), 2),
                "gpu_load_pct": round(statistics.mean(gpu)) if gpu else None, "samples": len(watts)}


DECODE_FLAGS = {"full": cv2.IMREAD_COLOR, "half": cv2.IMREAD_REDUCED_COLOR_2}


class Camera:
    """MJPEG camera. decode="opencv" lets OpenCV decode; "full" / "half" take the raw JPEG and decode it
    ourselves (half = libjpeg's built-in 1/2 scaling, much cheaper than decoding full size and resizing)."""

    def __init__(self, cap, decode):
        self.cap, self.flag = cap, DECODE_FLAGS.get(decode)

    def read(self):
        ok, frame = self.cap.read()
        if ok and self.flag is not None:
            frame = cv2.imdecode(frame.reshape(-1), self.flag)
            ok = frame is not None
        return ok, frame


def open_camera(device, size, decode, fps=30):
    w, h = map(int, size.split("x"))
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if decode != "opencv":
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)   # hand over the raw JPEG bytes
    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera {device}")
    return Camera(cap, decode)


class LatestFrame(threading.Thread):
    """Reads the camera in the background and keeps only the newest frame (like the live detector)."""

    def __init__(self, cap):
        super().__init__(daemon=True)
        self.cap, self.frame, self.count, self.running = cap, None, 0, True
        self.lock = threading.Lock()

    def run(self):
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                with self.lock:
                    self.frame, self.count = frame, self.count + 1

    def get(self):
        with self.lock:
            return self.frame, self.count


def summary(times_ms):
    times_ms = sorted(times_ms)
    return {"mean_ms": round(statistics.mean(times_ms), 2), "p50_ms": round(times_ms[len(times_ms) // 2], 2),
            "p95_ms": round(times_ms[int(len(times_ms) * 0.95)], 2), "fps": round(1000 / statistics.mean(times_ms), 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--capture", default="1920x1080", help="camera resolution (MJPEG)")
    ap.add_argument("--device", type=int, default=0, help="camera index")
    ap.add_argument("--decode", choices=["opencv", "full", "half"], default="opencv",
                    help="who decodes the MJPEG frames (see Camera)")
    ap.add_argument("--seconds", type=float, default=30, help="duration of each camera phase")
    ap.add_argument("--iters", type=int, default=300, help="model-only iterations")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", default="/out")
    args = ap.parse_args()

    power = Power()
    result = {"name": args.name, "model": args.model, "imgsz": args.imgsz, "capture": args.capture, "decode": args.decode,
              "measured_at": datetime.now().isoformat(timespec="seconds")}
    try:
        result["power_mode"] = Path("/logs/nvpmodel.txt").read_text().strip()
    except OSError:
        pass

    power.start()
    time.sleep(5)
    result["idle"] = power.stop()
    print("idle", result["idle"], flush=True)

    model = YOLO(args.model, task="detect")
    cap = open_camera(args.device, args.capture, args.decode)
    for _ in range(10):
        ok, frame = cap.read()
    if not ok:
        raise SystemExit("Camera gave no frames")

    # 1. Model only: the same camera frame over and over (preprocess + inference + postprocess)
    for _ in range(30):
        model.predict(frame, imgsz=args.imgsz, verbose=False)
    power.start()
    times = []
    for _ in range(args.iters):
        t = time.perf_counter()
        model.predict(frame, imgsz=args.imgsz, verbose=False)
        times.append((time.perf_counter() - t) * 1000)
    result["model_only"] = {**summary(times), **power.stop()}
    print("model_only", result["model_only"], flush=True)

    # 2. Camera only: frames read and decoded per second
    power.start()
    t0, n = time.perf_counter(), 0
    while time.perf_counter() - t0 < min(args.seconds, 10):
        n += cap.read()[0]
    result["camera_only"] = {"fps": round(n / (time.perf_counter() - t0), 1), **power.stop()}
    print("camera_only", result["camera_only"], flush=True)

    # 3. Camera + model: newest frame in, detections out, as fast as possible
    reader = LatestFrame(cap)
    reader.start()
    while reader.get()[0] is None:
        time.sleep(0.01)
    power.start()
    times, last, skipped = [], 0, 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < args.seconds:
        frame, count = reader.get()
        if count == last:          # no new frame yet
            time.sleep(0.001)
            continue
        skipped += count - last - 1
        last = count
        t = time.perf_counter()
        model.predict(frame, imgsz=args.imgsz, verbose=False)
        times.append((time.perf_counter() - t) * 1000)
    elapsed = time.perf_counter() - t0
    reader.running = False
    result["camera_and_model"] = {"processed_fps": round(len(times) / elapsed, 1),
                                  "camera_frames_skipped": skipped, "inference": summary(times), **power.stop()}
    print("camera_and_model", result["camera_and_model"], flush=True)

    out = Path(args.out) / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
