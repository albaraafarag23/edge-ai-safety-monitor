#!/usr/bin/env bash
# Downloads the two face recognition models into models/ (about 175 MB), see docs/faces.md.
#   scripts/get-face-models.sh [models folder]
#
# - face_detection_yunet_2023mar.onnx: YuNet face detector, from the OpenCV model zoo (MIT licence)
# - w600k_r50.onnx: ArcFace ResNet-50 trained on WebFace600K, from InsightFace's "buffalo_l" pack.
#   InsightFace's trained models are for non-commercial research use only: fine for this graduation
#   project, to be replaced (or licensed) before any commercial use.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:-models}"
mkdir -p "$DIR"

if [ ! -s "$DIR/face_detection_yunet_2023mar.onnx" ]; then
  curl -fL --retry 3 -o "$DIR/face_detection_yunet_2023mar.onnx" \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
fi
if [ ! -s "$DIR/w600k_r50.onnx" ]; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  curl -fL --retry 3 -o "$TMP/buffalo_l.zip" https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip
  python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extract('w600k_r50.onnx', sys.argv[2])" "$TMP/buffalo_l.zip" "$DIR"
fi
ls -l "$DIR"/face_detection_yunet_2023mar.onnx "$DIR"/w600k_r50.onnx
echo "Face models ready. Restart the detector: docker compose up -d cv_pipeline"
