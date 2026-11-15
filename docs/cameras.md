# More than one camera

One detector process serves every camera. The models are loaded once and take the cameras' newest frames in
turn, so a second camera costs frame rate, not memory: two cameras each get about half of what one camera gets.
Everything downstream already works per camera (rule timers and cooldowns, repeat suppression of emails,
snapshots and clips, the live view, incident filters and analytics).

## Setting them up
Copy `config/cameras.example.json` to `config/cameras.json` (git-ignored: a stream address can hold a password)
and list the cameras, then restart the detector (`docker compose up -d cv_pipeline`):

```json
[
  {"id": "cam_01", "source": "/dev/v4l/by-id/usb-Arducam_...-video-index0", "location": "Main gate"},
  {"id": "cam_02", "source": "rtsp://user:password@192.168.1.60:554/stream1", "location": "Yard"}
]
```

| Field | Meaning |
|---|---|
| `id` | Unique, 1-40 letters, digits, `-` or `_`. It is the `camera_id` in detections and incidents: don't rename a camera that has history |
| `source` | A USB camera (`/dev/v4l/by-id/...` is the stable name, `/dev/video2`, or an index), a network stream (`rtsp://`, `http://`) or a video file |
| `location` | Shown in the console ("Main gate") |
| `size`, `decode`, `controls` | USB cameras only; default to `CAMERA_SIZE`, `CAMERA_DECODE`, `CAMERA_CONTROLS` |
| `enabled` | `false` leaves the camera out without deleting its entry |

Without `config/cameras.json` there is one camera, from `CV_SOURCE` / `CAMERA_LOCATION` in `.env`, as before.
In test mode (`CV_TEST_MODE=true`) every listed camera sends synthetic frames, so the console can be tried
with several cameras and no hardware.

A camera that is missing at start, unplugged or whose stream drops doesn't stop the others: it shows as
offline in the console and is retried until it is back.

## In the console
- **Live cameras** shows every camera at once (pictures refreshed each second). Pick one to watch it live,
  see its incidents and edit its zones.
- **Zones are per camera.** A plugin zone exists on the camera the plugin names; draw it on another camera to
  use it there (`docs/plugins.md`).
- Rules and their settings (Safety rules page) apply to all cameras.

## The live view

The detector publishes an annotated picture of each camera up to `LIVE_FPS` (30) times a second, as a lighter JPEG
(`LIVE_QUALITY` 70; snapshots and clips keep quality 85); incident clips keep 10 a second. The console's live view gets them over a WebSocket (`GET /api/cameras/<id>/live`, same sign-in
and same-site check as the rest of the console): the server pushes each new picture and stops at `LIVE_WINDOW`
(4) that the browser hasn't shown yet, so pictures can't pile up in network buffers and fall seconds behind; a
slow link just gets fewer, always the newest. The browser decodes them in the background and paints them on a
canvas at the screen's refresh. Where WebSockets don't get through, it fetches the newest picture one by one.

A person who lacks required equipment gets it written on their own box, in red ("Person: no vest", or their
name when they are recognised). It comes from the rule engine, so it follows the zones and rule switches set in
the console; the model alone often draws no box for a missing vest, which is known from no vest being found.

Measured 2026-11-15: through the public address (Tailscale Funnel) a picture arrives 0.1–0.3 s after the camera
took it. With a 20 a second camera behind a 0.15 s round trip, the view shows 18.6 pictures a second (all sent),
evenly spaced (±12 ms); with the earlier window of 2 it was 11 a second (±36 ms).

Measured on the Jetson with the real camera, 2026-11-15, one viewer for 30 s through the public address:

| Live picture | Size | Pictures a second | Behind the camera (median / 95% / worst) | Stalls over 0.2 s |
|---|---|---|---|---|
| 20 a second, quality 85 (before) | 60 KB | 12.2 | 0.09 s / 0.89 s / 2.1 s | 15 |
| 20 a second, quality 70 | 33 KB | 16.6 | 0.07 s / 0.13 s / 0.23 s | 0 |
| 30 a second, quality 70 (now) | 33 KB | 19.7 | 0.05 s / 0.07 s / 0.19 s | 0 |

Straight to the Jetson (no internet) the heavier picture was already smooth, so the stalls came from the site's
upload line, not the Jetson: at 60 KB a picture the stream needed about 6 Mbit/s up. The lighter picture needs
about half. Publishing 30 a second costs the detector nothing (it still handled the camera's full 33 frames a
second). On a slower line, lower `LIVE_QUALITY` (e.g. 55) before anything else.

## On the Jetson
- USB cameras: two 1080p MJPEG cameras fit on the Jetson's USB 3 ports; find each camera's stable name with
  `ls /dev/v4l/by-id/`. The container already sees all of `/dev`.
- IP cameras: use the camera's lower-resolution sub-stream if the main one is 4K; frames are decoded on the
  CPU. A phone works as a test camera with any "IP camera" app that offers an RTSP or MJPEG address.
- Expect roughly the single-camera frame rate divided by the number of cameras (measured on the laptop: two
  15 fps video sources both kept up). Rules that time things (3 s without a hard hat) are unaffected, because
  they use each frame's time, not the frame count. Not yet measured on the Jetson with two real cameras.
- Several detectors sharing one Redis (e.g. a second Jetson): give each its own `DETECTOR_ID` and distinct
  camera ids.
