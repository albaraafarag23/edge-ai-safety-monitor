"""Reads one camera in a background thread and hands the detector the newest frame.

USB (UVC) cameras such as the Arducam IMX477 are opened in MJPEG mode at CAMERA_SIZE (OpenCV's default
would be 640x480). The raw JPEG is decoded here rather than by OpenCV: with CAMERA_DECODE=half, libjpeg
decodes straight to half size, which on the Jetson is what lets the detector keep up with all 30 fps
(OpenCV's own decode managed ~17 fps at 1080p). A 960 px model sees the same detail either way, because a
1920 px frame would be shrunk to 960 before inference anyway. `scale` maps boxes back to camera pixels,
so detections keep the camera's frame size (docs/contracts.md). The raw JPEG stays with the frame, so the
few things that need every pixel (face recognition) can decode it at full size (Frame.full()).

Other sources are read with plain cv2.VideoCapture at full size:
  - a network stream (rtsp://, http://, https://): live like a USB camera, reconnects when it drops
  - a video file: played at its own frame rate, so a recorded clip behaves like the live camera; ends at the end

A camera that is missing at start or drops out doesn't stop the detector: it is retried until it is back,
so the other cameras keep running (its live view shows offline meanwhile).
Measurements: jetson/README.md.
"""
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

DECODE_FLAGS = {"full": cv2.IMREAD_COLOR, "half": cv2.IMREAD_REDUCED_COLOR_2}
STREAM_PREFIXES = ("rtsp://", "rtsps://", "http://", "https://")
# IP cameras: TCP avoids the grey smeared frames UDP gives on a busy network
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


class CameraError(Exception):
    pass


@dataclass
class Frame:
    image: np.ndarray            # what the models see (half size with CAMERA_DECODE=half)
    scale: float                 # image pixels * scale = camera pixels
    raw: np.ndarray | None       # the camera's JPEG bytes, when the frame was decoded here
    n: int                       # counts up per camera

    def full(self) -> np.ndarray:
        """The frame at the camera's own resolution (decoded on demand, ~15 ms for 1080p on the Jetson)."""
        if self.raw is None or self.scale == 1.0:
            return self.image
        image = cv2.imdecode(self.raw, cv2.IMREAD_COLOR)
        return image if image is not None else self.image


def complete_jpeg(raw: np.ndarray) -> bool:
    """True if the camera's JPEG arrived whole: it ends with the end-of-image marker (FF D9), allowing for the
    zero padding some UVC cameras add. A frame cut off on the USB link would still decode, with its lower part
    grey ("Corrupt JPEG data: premature end of data segment"): people would vanish from it for a frame."""
    tail = raw[-64:]
    nz = np.flatnonzero(tail)
    if not len(nz):
        return False
    end = nz[-1]
    return end >= 1 and tail[end] == 0xD9 and tail[end - 1] == 0xFF


def safe_name(source) -> str:
    """The source without a stream's user:password, for logs."""
    text = str(source)
    if "://" in text and "@" in text:
        scheme, rest = text.split("://", 1)
        return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"
    return text


class Camera:
    def __init__(self, source: str, size: str = "1920x1080", fps: int = 30, decode: str = "half",
                 controls: str = "", wake: threading.Event | None = None):
        source = str(source)
        self.source = int(source) if source.isdigit() else source
        # a device index, /dev/videoN or (better) the camera's stable name under /dev/v4l/by-id/, which
        # survives the camera reconnecting as another /dev/videoN after a USB dropout
        self.is_device = isinstance(self.source, int) or self.source.startswith("/dev/")
        self.is_stream = not self.is_device and self.source.lower().startswith(STREAM_PREFIXES)
        self.is_file = not self.is_device and not self.is_stream
        self.name = safe_name(self.source)
        if decode not in ("opencv", *DECODE_FLAGS):
            raise ValueError(f"CAMERA_DECODE must be opencv, full or half, not '{decode}'")
        self.flag = DECODE_FLAGS.get(decode) if self.is_device else None
        self.scale = 2.0 if self.flag == cv2.IMREAD_REDUCED_COLOR_2 else 1.0
        self.width, self.height = map(int, size.lower().split("x"))
        self.fps = fps
        self.controls = controls

        self.cap = None
        self._frame: Frame | None = None
        self._count, self._ended = 0, False
        self._damaged, self._damaged_logged = 0, 0.0
        self._damaged_since = time.monotonic()
        self._lock = threading.Condition()
        self._wake = wake    # set on every new frame: one detector loop can wait on several cameras
        threading.Thread(target=self._read_loop, daemon=True, name=f"camera-{self.name}").start()

    def _open(self):
        if not self.is_device:
            cap = cv2.VideoCapture(self.source)
            if self.is_stream:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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
            cap.release()
            raise CameraError(f"[CV] Cannot open camera source {self.name}")
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w and h:
            self.width, self.height = w, h   # what the camera agreed to, or the video's own size
        if self.is_file:
            self.fps = cap.get(cv2.CAP_PROP_FPS) or self.fps
        print(f"[CV] Camera {self.name}: {w}x{h}"
              + (f" MJPEG, decoded at {w // int(self.scale)}x{h // int(self.scale)}" if self.flag is not None else ""),
              flush=True)
        return cap

    def _read(self):
        """(ok, frame, raw). ok is None for a damaged frame: skipped, but the camera is fine."""
        ok, frame = self.cap.read()
        raw = None
        if ok and self.flag is not None:
            raw = frame.reshape(-1)
            if not complete_jpeg(raw):
                return None, None, None
            frame = cv2.imdecode(raw, self.flag)
            ok = frame is not None
        return ok, frame, raw

    def _skip_damaged(self):
        self._damaged += 1
        now = time.monotonic()
        if now - self._damaged_logged >= 300:
            print(f"[CV] Camera {self.name}: skipped {self._damaged} cut-off frame(s) (USB) "
                  f"in the last {now - self._damaged_since:.0f} s", flush=True)
            self._damaged, self._damaged_logged, self._damaged_since = 0, now, now

    def _end(self):
        with self._lock:
            self._ended = True
            self._lock.notify_all()
        if self._wake:
            self._wake.set()

    def _read_loop(self):
        failures = 0
        next_frame = time.monotonic()
        while True:
            if self.cap is None:
                try:
                    self.cap = self._open()
                    next_frame = time.monotonic()
                except CameraError as e:
                    if self.is_file:     # a video that can't be opened never will be
                        print(e, flush=True)
                        return self._end()
                    failures += 1
                    if failures in (1, 10) or failures % 60 == 0:
                        print(f"{e} (attempt {failures}), retrying", flush=True)
                    time.sleep(min(failures, 5))
                    continue
            ok, frame, raw = self._read()
            if ok is None:
                self._skip_damaged()
                continue
            if ok:
                failures = 0
                if self.is_file:   # play files back in real time, like a live camera,
                    next_frame += 1 / self.fps   # so duration rules (e.g. 3 s without a hard hat) still work
                    time.sleep(max(0.0, next_frame - time.monotonic()))
                with self._lock:
                    self._count += 1
                    self._frame = Frame(frame, self.scale, raw, self._count)
                    self._lock.notify_all()
                if self._wake:
                    self._wake.set()
                continue
            if self.is_file:             # end of a video file
                return self._end()
            failures += 1                # unplugged, stream dropped or a glitch: reopen after a pause
            if failures in (1, 10) or failures % 60 == 0:
                print(f"[CV] Camera {self.name}: no frame ({failures}), reopening", flush=True)
            time.sleep(1)
            self.cap.release()
            self.cap = None

    def poll(self, last: int) -> Frame | None:
        """The newest frame if it is newer than frame number `last`, else None. Never waits."""
        with self._lock:
            return self._frame if self._frame is not None and self._count != last else None

    @property
    def count(self) -> int:
        """Frames read from the camera so far."""
        return self._count

    @property
    def ended(self) -> bool:
        """True once a video file has played to its end (cameras and streams never end)."""
        return self._ended

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
    try:
        result = subprocess.run(["v4l2-ctl", "-d", dev, "-c", controls], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[CV] Camera controls {controls}: {e}", flush=True)
        return
    print(f"[CV] Camera controls {controls}: " + ("set" if result.returncode == 0 else result.stderr.strip()),
          flush=True)
