"""Training set for the final "is this a person LYING down?" check (sitting does not count).

    python training/build_lying_set.py [--out data/lying_verify]

  lying       data/down_verify/*/down (fall_fyp people as the fall detector cuts them out, build_down_crops.py)
              WITHOUT the ones that look clearly sitting / kneeling (see below), plus the "lie" crops of
              data/posture_crops (build_posture_crops.py: a high indoor camera)
  not_lying   data/down_verify/*/not_down (the fall detector's false boxes, upright site workers, hospital
              staff) plus the sit / bend / stand crops of data/posture_crops

fall_fyp marks people sitting on the ground after a fall as fallen too (85 of 378 reviewed test people). They
are dropped from "lying" when the pose model finds a clearly upright torso that is the boxed person (its box
covers >= MIN_IOU of the box's own area inside the crop), torso within UPRIGHT_DEG of vertical, knees or ankles
found. Tuned against the hand review of the fall_fyp test people (outputs/eval/fall_test_posture.json): it drops
about half of the sitting people and one in seven lying ones, so the "lying" set ends up with fewer sitters;
the rest of the work is done by the sitting examples in "not_lying". Files are hard-linked, not copied.
"""
import argparse
import json
import math
import os
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
PAD = 0.2           # build_down_crops.py's margin: the boxed person is the middle 1/1.4 of the crop
MIN_IOU = 0.6
UPRIGHT_DEG = 30


def iou(a, b):
    ix, iy = max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def mid(k, a, b):
    pts = [k[i][:2] for i in (a, b) if k[i][2] >= 0.5]
    return None if not pts else (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def clearly_sitting(result, w, h) -> bool:
    m = PAD / (1 + 2 * PAD)
    inner = [m * w, m * h, (1 - m) * w, (1 - m) * h]
    best = max(zip(result.boxes.xyxy.tolist(), result.keypoints.data.tolist()),
               key=lambda bk: iou(bk[0], inner), default=None)
    if best is None or iou(best[0], inner) < MIN_IOU:
        return False
    k = best[1]
    sh, hp = mid(k, 5, 6), mid(k, 11, 12)
    if sh is None or hp is None:
        return False
    dx, dy = hp[0] - sh[0], hp[1] - sh[1]
    if dy <= 0 or math.degrees(math.atan2(abs(dx), dy)) >= UPRIGHT_DEG:
        return False
    return mid(k, 13, 14) is not None or mid(k, 15, 16) is not None


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        os.link(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/lying_verify")
    ap.add_argument("--pose", default="models/yolo11m-pose.pt")
    a = ap.parse_args()
    out, pose = ROOT / a.out, YOLO(str(ROOT / a.pose))
    n = {"dropped_as_sitting": 0}

    def add(src, split, label):
        link(src, out / split / label / src.name)
        n[f"{split}/{label}"] = n.get(f"{split}/{label}", 0) + 1

    for split in ("train", "val"):
        downs = sorted((ROOT / "data/down_verify" / split / "down").glob("*.jpg"))
        for s in range(0, len(downs), 32):
            batch = downs[s:s + 32]
            imgs = [cv2.imread(str(p)) for p in batch]
            for p, img, r in zip(batch, imgs, pose.predict(imgs, conf=0.25, verbose=False)):
                if clearly_sitting(r, img.shape[1], img.shape[0]):
                    n["dropped_as_sitting"] += 1
                else:
                    add(p, split, "lying")
        for p in sorted((ROOT / "data/down_verify" / split / "not_down").glob("*.jpg")):
            add(p, split, "not_lying")
        for posture in ("lie", "sit", "bend", "stand"):
            for p in sorted((ROOT / "data/posture_crops" / split / posture).glob("*.jpg")):
                add(p, split, "lying" if posture == "lie" else "not_lying")
    (out / "build.json").write_text(json.dumps({"pose": a.pose, "min_iou": MIN_IOU, "upright_deg": UPRIGHT_DEG,
                                                "counts": n}, indent=2))
    print(json.dumps(n, indent=2))


if __name__ == "__main__":
    main()
