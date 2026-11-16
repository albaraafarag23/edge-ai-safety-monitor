#!/usr/bin/env python3
"""Lends this computer's camera to a SiteSentry box as an extra camera, for testing several cameras.

    python scripts/webcam-stream.py                  # camera 0, 1080p, on this machine's Tailscale address
Prints the address to put in the box's config/cameras.json, e.g.
    {"id": "cam_02", "source": "http://100.77.27.75:8090/<token>/stream.mjpg", "location": "Laptop"}

It serves the camera's own JPEGs as an MJPEG stream (no re-encoding), only on the Tailscale address, under a
random token. Stop it with Ctrl+C; the camera light goes off.
"""
import argparse
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2


def tailscale_ip() -> str:
    out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True).stdout.split()
    if not out:
        raise SystemExit("No Tailscale address here; pass --host.")
    return out[0]


class Camera:
    def __init__(self, index: int, width: int, height: int, fps: int):
        self.cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)   # the camera's own JPEG bytes
        if not self.cap.isOpened():
            raise SystemExit(f"Camera {index} can't be opened (in use by another program?)")
        self.jpeg, self.count = b"", 0
        self.new = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            data = frame.tobytes()
            if data[:2] != b"\xff\xd8":   # not a JPEG (the camera fell back to raw): encode it
                ok, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                data = enc.tobytes() if ok else b""
            with self.new:
                self.jpeg, self.count = data, self.count + 1
                self.new.notify_all()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--host", help="address to listen on (default: this machine's Tailscale address)")
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    width, height = map(int, args.size.split("x"))
    host = args.host or tailscale_ip()
    token = secrets.token_urlsafe(12)
    camera = Camera(args.camera, width, height, args.fps)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path != f"/{token}/stream.mjpg":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            print(f"Viewer connected: {self.client_address[0]}", flush=True)
            seen = 0
            try:
                while True:
                    with camera.new:
                        camera.new.wait_for(lambda: camera.count != seen, timeout=5)
                        jpeg, seen = camera.jpeg, camera.count
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                print(f"Viewer left: {self.client_address[0]}", flush=True)

    server = ThreadingHTTPServer((host, args.port), Handler)
    print(f"Streaming camera {args.camera} ({args.size}) at http://{host}:{args.port}/{token}/stream.mjpg", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
