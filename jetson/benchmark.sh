#!/bin/bash
# Run jetson/benchmark.py in the Ultralytics Jetson container with board power logging.
# Run on the Jetson from ~/sitesentry (models in ./models, results in ./benchmarks):
#   bash benchmark.sh /models/construction_ppe.engine --imgsz 960 --name engine_960_1080p
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=${IMAGE:-ultralytics/ultralytics:latest-jetson-jetpack6}
# the camera's stable name (it can come back as /dev/video1 after a USB reconnect)
CAM=$(readlink -f "${CAMERA:-$(ls /dev/v4l/by-id/*-video-index0 | head -1)}")
mkdir -p logs benchmarks
v4l2-ctl -d "$CAM" -c power_line_frequency=1 2>/dev/null || true   # 50 Hz mains (Egypt)
nvpmodel -q 2>/dev/null | head -1 | sed 's/NV Power Mode: //' > logs/nvpmodel.txt
tegrastats --interval 500 > logs/tegrastats.log &
TS=$!
trap 'kill $TS 2>/dev/null' EXIT
docker run --rm --ipc=host --runtime nvidia --device "$CAM:/dev/video0" \
  -v "$PWD/models:/models" -v "$PWD/logs:/logs:ro" -v "$PWD/benchmarks:/out" -v "$PWD/benchmark.py:/app/benchmark.py:ro" \
  -w /app "$IMAGE" python3 benchmark.py "$@" 2>&1 | grep -vE "Ultralytics Settings|yolo settings|docs.ultralytics.com/usage"
