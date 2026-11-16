"""Is the "person down" detector better than the pose rule (posture.py)? Three checks, written to outputs/eval/:

  1. real falls: the 422 fallen people in data/fall_fyp/test (how many are caught);
  2. upright workers: the Construction Site Safety test photos (how many people are wrongly called down);
  3. empty rooms: pictures with nobody in them (e.g. the dark-room frames that once gave false alarms).

    python training/eval_person_down.py outputs/runs/person_down_s/weights/best.pt --empty <folder of jpgs>
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cv_pipeline"))
from posture import is_lying  # noqa: E402


def iou(a, b):
    ix, iy = max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def labels(path, w, h):
    out = []
    lab = Path(path.replace("/images/", "/labels/")).with_suffix(".txt")
    for line in (lab.read_text().split("\n") if lab.exists() else []):
        p = line.split()
        if len(p) == 5:
            _, cx, cy, bw, bh = map(float, p)
            out.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--conf", type=float, nargs="+", default=[0.3, 0.4, 0.5, 0.6])
    ap.add_argument("--pose", default="models/yolo11n-pose.pt")
    ap.add_argument("--empty", default=None, help="folder of pictures with nobody down in them")
    args = ap.parse_args()
    down, pose = YOLO(args.model), YOLO(args.pose)
    falls = sorted(glob.glob("data/fall_fyp/test/images/*.jpg"))
    upright = sorted(glob.glob("data/construction-site-safety/test/images/*.jpg"))
    empty = sorted(glob.glob(f"{args.empty}/*.jpg")) if args.empty else []
    low = min(args.conf)
    res = {c: {"falls_caught": 0, "upright_false": 0, "empty_false": 0} for c in args.conf}
    res["pose"] = {"falls_caught": 0, "upright_false": 0, "empty_false": 0}
    total_falls = 0
    for path in falls:
        img = cv2.imread(path)
        gts = labels(path, img.shape[1], img.shape[0])
        total_falls += len(gts)
        d = down.predict(img, conf=low, verbose=False)[0]
        boxes = list(zip(d.boxes.xyxy.tolist(), d.boxes.conf.tolist()))
        p = pose.predict(img, conf=0.5, verbose=False)[0]
        lying = [b for b, k in zip(p.boxes.xyxy.tolist(), p.keypoints.data.tolist())
                 if is_lying(b, k)] if p.keypoints is not None else []
        for g in gts:
            for c in args.conf:
                res[c]["falls_caught"] += any(iou(g, b) >= 0.3 and s >= c for b, s in boxes)
            res["pose"]["falls_caught"] += any(iou(g, b) >= 0.3 for b in lying)
    for group, paths in (("upright_false", upright), ("empty_false", empty)):
        for path in paths:
            img = cv2.imread(path)
            d = down.predict(img, conf=low, verbose=False)[0]
            for c in args.conf:
                res[c][group] += sum(s >= c for s in d.boxes.conf.tolist())
            p = pose.predict(img, conf=0.5, verbose=False)[0]
            if p.keypoints is not None:
                res["pose"][group] += sum(is_lying(b, k) for b, k in zip(p.boxes.xyxy.tolist(), p.keypoints.data.tolist()))
    summary = {"model": args.model, "fallen_people": total_falls, "upright_photos": len(upright),
               "empty_photos": len(empty),
               "results": {str(k): {**v, "falls_caught_pct": round(100 * v["falls_caught"] / max(total_falls, 1), 1)}
                           for k, v in res.items()}}
    out = Path("outputs/eval/person_down.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
