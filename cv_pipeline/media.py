"""Saves a snapshot and a short video clip for every incident on this camera.

The detector keeps the last BUFFER_SECONDS of frames (with boxes drawn on them) in memory,
downscaled and JPEG-compressed so it stays small (~10 MB). A background thread listens on
the incidents stream. For each incident on this camera it writes:
  - the frame the rule fired on -> incident["snapshot_url"]
  - PRE_SECONDS before to POST_SECONDS after that frame -> incident["clip_url"]
Files are written under a temporary name and renamed, so readers never see half a file.
"""
import collections
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import redis

BUFFER_SECONDS = 12
BUFFER_FPS = 10        # frames kept per second (camera may run faster)
MAX_WIDTH = 960        # buffered frames are downscaled to this width
PRE_SECONDS = 5
POST_SECONDS = 3
INCIDENT_STREAM = "incidents"

# ffmpeg with the libx264 encoder, bundled by the imageio-ffmpeg package. H.264 plays in every
# browser and email app; OpenCV's own pip build can only write MPEG-4, which browsers won't play.
try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = None

COLORS = {"Person": (255, 160, 0), "Hardhat": (0, 200, 0), "Safety Vest": (0, 200, 0),
          "NO-Hardhat": (0, 0, 255), "NO-Safety Vest": (0, 0, 255)}
DEFAULT_COLOR = (0, 215, 255)


def annotate(image, detections, scale):
    for d in detections:
        x1, y1, x2, y2 = (int(v * scale) for v in d["bbox"])
        color = COLORS.get(d["class_name"], DEFAULT_COLOR)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        label = f"{d['class_name']} {d['confidence']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(image, (x1, max(y1 - th - 6, 0)), (x1 + tw + 4, max(y1, th + 6)), color, -1)
        cv2.putText(image, label, (x1 + 2, max(y1 - 4, th + 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1, cv2.LINE_AA)
    return image


def _atomic_write(path: Path, write):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".part-{path.name}")
    if not write(tmp):
        tmp.unlink(missing_ok=True)
        return False
    os.replace(tmp, path)
    return True


class MediaRecorder:
    def __init__(self, media_dir: str, redis_url: str, camera_id: str):
        self.media_dir = Path(media_dir)
        self.redis_url = redis_url
        self.camera_id = camera_id
        self._frames = collections.deque()   # (frame_id, time, jpeg bytes)
        self._lock = threading.Lock()
        self._last_add = 0.0

    # ---------- called by the detector for every frame ----------
    def add(self, frame_id: int, image, detections: list[dict]):
        now = time.time()
        if now - self._last_add < 1 / BUFFER_FPS:
            return
        self._last_add = now
        h, w = image.shape[:2]
        scale = min(1.0, MAX_WIDTH / w)
        small = cv2.resize(image, (int(w * scale), int(h * scale))) if scale < 1 else image.copy()
        ok, jpg = cv2.imencode(".jpg", annotate(small, detections, scale), [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return
        with self._lock:
            self._frames.append((frame_id, now, jpg.tobytes()))
            while self._frames and self._frames[0][1] < now - BUFFER_SECONDS:
                self._frames.popleft()

    # ---------- incident listener ----------
    def start(self):
        threading.Thread(target=self._listen, daemon=True, name="media-listener").start()

    def _listen(self):
        r = redis.from_url(self.redis_url, decode_responses=True)
        group = f"media_{self.camera_id}"
        try:
            r.xgroup_create(INCIDENT_STREAM, group, id="$", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
        print(f"[CV] Media recorder ready ({MEDIA_SUMMARY}) -> {self.media_dir}", flush=True)
        while True:
            try:
                messages = r.xreadgroup(group, "detector", {INCIDENT_STREAM: ">"}, count=10, block=1000)
                for _, entries in messages or []:
                    for msg_id, data in entries:
                        try:
                            incident = json.loads(data["data"])
                            if incident.get("camera_id") == self.camera_id:
                                self._save(incident)
                        except Exception as e:  # never let one bad incident stop the recorder
                            print(f"[CV] Media: could not save for message {msg_id}: {e}", flush=True)
                        r.xack(INCIDENT_STREAM, group, msg_id)
            except redis.exceptions.ConnectionError as e:
                print(f"[CV] Media: Redis connection lost ({e}), retrying", flush=True)
                time.sleep(2)

    def _path(self, url: str | None) -> Path | None:
        if not url or not url.startswith("/media/"):
            return None
        return self.media_dir / url.removeprefix("/media/")

    def _save(self, incident: dict):
        target = (incident.get("metadata") or {}).get("frame_id")
        with self._lock:
            frames = list(self._frames)
        if not frames:
            print(f"[CV] Media: no buffered frames for {incident['event_id']}", flush=True)
            return
        # the buffered frame closest to the one the rule fired on (buffer is subsampled)
        center = min(frames, key=lambda f: abs(f[0] - target)) if target is not None else frames[-1]

        snapshot = self._path(incident.get("snapshot_url"))
        if snapshot:
            _atomic_write(snapshot, lambda p: p.write_bytes(center[2]) > 0)
            print(f"[CV] Saved snapshot {snapshot.name}", flush=True)

        clip = self._path(incident.get("clip_url"))
        if clip:
            # wait for the frames after the incident, then write the clip
            threading.Timer(POST_SECONDS, self._save_clip, args=(clip, center[1])).start()

    def _save_clip(self, path: Path, t_center: float):
        with self._lock:
            frames = [f for f in self._frames if t_center - PRE_SECONDS <= f[1] <= t_center + POST_SECONDS]
        if not frames:
            return
        images = [cv2.imdecode(np.frombuffer(f[2], np.uint8), cv2.IMREAD_COLOR) for f in frames]
        # play back at the rate frames were actually captured (the detector may run below BUFFER_FPS)
        span = frames[-1][1] - frames[0][1]
        fps = (len(frames) - 1) / span if len(frames) > 1 and span > 0 else 1.0

        if FFMPEG and _atomic_write(path, lambda tmp: _write_h264(tmp, images, fps)):
            codec = "H.264"
        elif _atomic_write(path, lambda tmp: _write_mpeg4(tmp, images, fps)):
            codec = "MPEG-4 (won't play in browsers)"
        else:
            print(f"[CV] Media: could not write clip {path.name}", flush=True)
            return
        print(f"[CV] Saved clip {path.name} ({len(images)} frames, {span:.1f} s at {fps:.1f} fps, {codec})", flush=True)


def _write_h264(tmp: Path, images: list, fps: float) -> bool:
    h, w = images[0].shape[:2]
    cmd = [FFMPEG, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:.3f}", "-i", "-",
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # H.264 with yuv420p needs even dimensions
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
           "-pix_fmt", "yuv420p",        # the colour format browsers can decode
           "-movflags", "+faststart",    # index at the start, so playback begins before the download ends
           str(tmp)]
    try:
        data = b"".join((img if img.shape[:2] == (h, w) else cv2.resize(img, (w, h))).tobytes() for img in images)
        result = subprocess.run(cmd, input=data, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[CV] Media: ffmpeg failed ({e}), falling back to MPEG-4", flush=True)
        return False
    if result.returncode != 0:
        print(f"[CV] Media: ffmpeg failed ({result.stderr.decode(errors='replace').strip()[:200]}), "
              f"falling back to MPEG-4", flush=True)
        return False
    return True


def _write_mpeg4(tmp: Path, images: list, fps: float) -> bool:
    h, w = images[0].shape[:2]
    out = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not out.isOpened():
        return False
    for img in images:
        out.write(img if img.shape[:2] == (h, w) else cv2.resize(img, (w, h)))
    out.release()
    return True


MEDIA_SUMMARY = (f"buffer {BUFFER_SECONDS}s @ {BUFFER_FPS} fps, clips {PRE_SECONDS}s before + {POST_SECONDS}s after, "
                 f"{'H.264 via ffmpeg' if FFMPEG else 'MPEG-4 (ffmpeg not found)'}")
