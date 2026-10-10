# Jetson Orin Nano: setup, TensorRT and measurements

The whole system runs on the Jetson: camera → detector (GPU, TensorRT) → rules → dashboard, reports and email.

## Device

| | |
|---|---|
| Board | Jetson Orin Nano (Super) dev kit, 7.6 GB RAM shared by CPU and GPU |
| Software | JetPack 6.2 (L4T R36.4.7), CUDA 12.6, TensorRT 10.3 (10.7 inside the container) |
| Storage | System on the SD card; Docker data and `~/sitesentry` on the NVMe SSD (`/mnt/ssd`) |
| Camera | Arducam 12MP IMX477 USB (UVC), 1080p MJPEG at 30 fps |
| Power mode | **25 W** (`sudo nvpmodel -m 1`), see below |

## One-time setup

1. **SSD**: mount the NVMe SSD at `/mnt/ssd` (fstab, by UUID) and set Docker's `data-root` to `/mnt/ssd/docker`
   and `default-runtime` to `nvidia` in `/etc/docker/daemon.json`. The SD card is too slow for 15 GB images.
2. Add the user to the `docker` group, install `v4l-utils`.
3. `docker pull ultralytics/ultralytics:latest-jetson-jetpack6` (7.3 GB download, 15 GB on disk).
4. Copy the repo to `~/sitesentry/app` (without `data/`, `outputs/`) and the `.pt` models to `~/sitesentry/models`
   (`app/models` is a link to it). In `.env`: `CV_TEST_MODE=false`, no `CV_SOURCE`.

## TensorRT models

TensorRT builds are tied to the device and TensorRT version, so they are built on the Jetson, not copied:

```bash
docker run --rm --ipc=host -v ~/sitesentry/models:/models ultralytics/ultralytics:latest-jetson-jetpack6 \
  yolo export model=/models/construction_ppe.pt format=engine half=True imgsz=960 device=0 batch=1 workspace=4
```

Same for `smoking.pt` (imgsz 640). Takes 7–11 minutes per model. Close the browser and other apps first: with
too little free memory TensorRT skips its faster options. With `MODEL_FORMAT=engine` the detector uses
`<model>.engine` next to each `<model>.pt` named in the plugin.

Accuracy is unchanged (82 test images, Construction Site Safety v28):

| 960 model on the Jetson | mAP50 | mAP50-95 | NO-Hardhat mAP50 |
|---|---|---|---|
| PyTorch `.pt` | 0.848 | 0.563 | 0.605 |
| TensorRT FP16 `.engine` | 0.843 | 0.563 | 0.599 |

## Run

```bash
cd ~/sitesentry/app
docker compose -f docker-compose.yml -f docker-compose.jetson.yml up -d --build
```

The dashboard listens on the Jetson's `127.0.0.1:3000` only. From the laptop:
`ssh -L 3001:localhost:3000 jetson`, then open http://localhost:3001.

The camera is opened by its stable name (`/dev/v4l/by-id/...-video-index0`): after a USB dropout it can come
back as `/dev/video1`. The container sees all of `/dev` with permission for video devices, and the detector
reopens the camera and re-applies its settings (50 Hz anti-flicker) by itself.

## Speed and power

`benchmark.sh` runs `benchmark.py` in the container and logs board power with `tegrastats` (VDD_IN = whole
module). Results in `~/sitesentry/benchmarks/` (copies in `outputs/jetson/`). Camera 1080p MJPEG, real scene.

| Setup | Camera → detection | Time per frame (mean / p95) | Board power | GPU load |
|---|---|---|---|---|
| 960 model, OpenCV decodes 1080p (the old way) | 16.6 fps | 44 / 47 ms | 8.1 W | 49 % |
| 960 model, capture at 720p | 18.7 fps | 53 / 57 ms | 8.3 W | 56 % |
| 960 model, we decode 1080p at full size | 28.6 fps | 35 / 38 ms | 11.4 W | 60 % |
| **960 model, we decode 1080p at half size** (MAXN SUPER) | **33.1 fps** | **27 / 27 ms** | 12.0 W | 64 % |
| **same, 25 W mode** (in use) | **33.0 fps** | **27 / 30 ms** | 12.0 W | 66 % |
| 640 model, half-size decode (MAXN SUPER) | 27.9 fps | 36 / 36 ms | 7.4 W | 59 % |

Idle: 5.3 W. The camera delivers 30 fps (33 measured), so the detector now handles every frame.

What we learned:
- **The camera decode was the bottleneck, not the model.** OpenCV's own MJPEG decode inside the container
  reached only ~17 fps at 1080p. Taking the raw JPEG and decoding it ourselves at half size (libjpeg's built-in
  1/2 scaling, 8.7 ms instead of 15.3 ms at full size) gives a 960×540 frame, which is exactly what the 960 model
  needs, so the model sees the same detail. Boxes are scaled ×2 back to camera pixels (`cv_pipeline/camera.py`).
- **Exact halving is fast, other resize factors are not**: shrinking 1080p to 960 took 8.7 ms, 720p to 960
  took 19 ms. That is also why the 640 model is *slower* end to end than the 960 one here (960 → 640 resize),
  so the 960 model stays: more accurate and faster.
- **25 W vs MAXN SUPER**: identical frame rate, because the camera is the limit. MAXN SUPER triggers the
  board's over-current protection ("System throttled due to over-current"; ~2 events per benchmark run, ~120
  during TensorRT builds), 25 W didn't trigger it once. Use 25 W.

Extra models (smoking, `smoking.engine`) run on the same frames and add their own time per frame.
