"""Publishes the latest annotated frame and a status hash to Redis, for the dashboard's live view.

Only the newest frame is kept (one key per camera) and both keys expire after a few seconds, so
a stopped detector shows as offline. The backend reads them in backend/cameras.py.
Redis errors are logged and skipped: the live view must never stop detection.
"""
import time
from datetime import datetime, timezone

import redis

KEY_TTL_S = 5
INFO_EVERY_S = 1.0


class LiveView:
    def __init__(self, redis_url: str, camera_id: str, plugin_id: str, mode: str, location: str | None = None):
        self.r = redis.from_url(redis_url)  # binary: frames are JPEG bytes
        self.camera_id = camera_id
        self.info = {"camera_id": camera_id, "plugin_id": plugin_id, "mode": mode, "model": ""}
        if location:
            self.info["location"] = location
        self._frames = 0
        self._window_start = time.time()
        self._last_info = 0.0
        self._fps = 0.0
        self._error_logged = False

    def set_model(self, model: str):
        self.info["model"] = model

    def frame_processed(self):
        """Call once per detector frame; measures the detector's real frame rate."""
        self._frames += 1
        now = time.time()
        if now - self._window_start >= 2:
            self._fps = self._frames / (now - self._window_start)
            self._frames, self._window_start = 0, now

    def publish(self, jpeg: bytes, width: int, height: int):
        """Latest annotated frame (called by MediaRecorder, at most BUFFER_FPS times a second)."""
        prefix = f"camera:{self.camera_id}"
        try:
            pipe = self.r.pipeline()
            pipe.set(f"{prefix}:frame", jpeg, ex=KEY_TTL_S)
            now = time.time()
            if now - self._last_info >= INFO_EVERY_S:
                self._last_info = now
                pipe.sadd("cameras", self.camera_id)
                pipe.hset(f"{prefix}:info", mapping={
                    **self.info, "fps": f"{self._fps:.1f}", "width": width, "height": height,
                    "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                })
                pipe.expire(f"{prefix}:info", KEY_TTL_S)
            pipe.execute()
            self._error_logged = False
        except redis.exceptions.RedisError as e:
            if not self._error_logged:
                print(f"[CV] Live view: Redis error ({e}); detection continues", flush=True)
                self._error_logged = True
