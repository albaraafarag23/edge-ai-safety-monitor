"""Reads the camera in a background thread and hands the detector the newest frame.

USB (UVC) cameras such as the Arducam IMX477 are opened in MJPEG mode at CAMERA_SIZE (OpenCV's default
would be 640x480). The raw JPEG is decoded here rather than by OpenCV: with CAMERA_DECODE=half, libjpeg
decodes straight to half size, which on the Jetson is what lets the detector keep up with all 30 fps
(OpenCV's own decode managed ~17 fps at 1080p). A 960 px model sees the same detail either way, because a
1920 px frame would be shrunk to 960 before inference anyway. `scale` maps boxes back to camera pixels,
so detections keep the camera's frame size (docs/contracts.md).

Any other source (a video file, an RTSP URL) is read with plain cv2.VideoCapture at full size, at its own
frame rate, so a recorded clip behaves like the live camera.
Measurements: jetson/README.md.
"""
import os
import shutil
import subprocess
import threading
import time

import cv2

DECODE_FLAGS = {"full": cv2.IMREAD_COLOR, "half": cv2.IMREAD_REDUCED_COLOR_2}


class Camera:
    def __init__(self, source: str, size: str = "1920x1080", fps: int = 30, decode: str = "half",
                 controls: str = ""):
        self.source = int(source) if source.isdigit() else source
        # a device index, /dev/videoN or (better) the camera's stable name under /dev/v4l/by-id/, which
        # survives the camera reconnecting as another /dev/videoN after a USB dropout
        self.is_device = isinstance(self.source, int) or self.source.startswith("/dev/")
        if decode not in ("opencv", *DECODE_FLAGS):
            raise ValueError(f"CAMERA_DECODE must be opencv, full or half, not '{decode}'")
        self.flag = DECODE_FLAGS.get(decode) if self.is_device else None
        self.scale = 2.0 if self.flag == cv2.IMREAD_REDUCED_COLOR_2 else 1.0
        self.width, self.height = map(int, size.lower().split("x"))
        self.fps = fps
        self.controls = controls

        self.cap = self._open()
        self._frame, self._count, self._ended = None, 0, False
        self._lock = threading.Condition()
        threading.Thread(target=self._read_loop, daemon=True, name="camera").start()

    def _open(self):
        if not self.is_device:
            cap = cv2.VideoCapture(self.source)
        else:
            device = os.path.realpath(self.source) if isinstance(self.source, str) else self.source
            if self.controls:   # re-applied on every (re)open: the camera forgets them when it reconnects
                set_controls(device, self.controls)
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if self.flag is not None:
                cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)   # hand over the raw JPEG bytes
        if not cap.isOpened():
            raise SystemExit(f"[CV] Cannot open camera source {self.source}")
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w and h:
            self.width, self.height = w, h   # what the camera agreed to, or the video's own size
        if not self.is_device:
            self.fps = cap.get(cv2.CAP_PROP_FPS) or self.fps
        print(f"[CV] Camera {self.source}: {w}x{h}"
              + (f" MJPEG, decoded at {w // int(self.scale)}x{h // int(self.scale)}" if self.flag is not None else ""),
              flush=True)
        return cap

    def _read(self):
        ok, frame = self.cap.read()
        if ok and self.flag is not None:
            frame = cv2.imdecode(frame.reshape(-1), self.flag)
            ok = frame is not None
        return ok, frame

    def _read_loop(self):
        failures = 0
        next_frame = time.monotonic()
        while True:
            ok, frame = self._read()
            if ok:
                failures = 0
                if not self.is_device:   # play files and streams back in real time, like a live camera,
                    next_frame += 1 / self.fps   # so duration rules (e.g. 3 s without a hard hat) still work
                    time.sleep(max(0.0, next_frame - time.monotonic()))
                with self._lock:
                    self._frame, self._count = frame, self._count + 1
                    self._lock.notify_all()
                continue
            if not self.is_device:       # end of a video file
                with self._lock:
                    self._ended = True
                    self._lock.notify_all()
                return
            failures += 1                # unplugged or glitch: reopen after a pause
            if failures in (1, 10) or failures % 60 == 0:
                print(f"[CV] Camera {self.source}: no frame ({failures}), reopening", flush=True)
            time.sleep(1)
            self.cap.release()
            try:
                self.cap = self._open()
            except SystemExit as e:
                print(e, flush=True)

    def frames(self):
        """Yields each new frame once (the newest one: frames that arrive while the detector is busy are skipped)."""
        last = 0
        while True:
            with self._lock:
                self._lock.wait_for(lambda: self._count != last or self._ended)
                if self._count == last:
                    return
                frame, last = self._frame, self._count
            yield frame

    @property
    def frame_size(self) -> tuple[int, int]:
        """Camera resolution, which is what detection boxes refer to."""
        return self.width, self.height


def set_controls(device, controls: str):
    """Camera controls via v4l2-ctl, e.g. "power_line_frequency=1" (50 Hz mains, Egypt). They reset when
    the camera is unplugged, so they're applied on every start."""
    if not shutil.which("v4l2-ctl"):
        print("[CV] v4l2-ctl not installed, camera controls not applied", flush=True)
        return
    dev = f"/dev/video{device}" if isinstance(device, int) else device
    result = subprocess.run(["v4l2-ctl", "-d", dev, "-c", controls], capture_output=True, text=True)
    print(f"[CV] Camera controls {controls}: " + ("set" if result.returncode == 0 else result.stderr.strip()),
          flush=True)
