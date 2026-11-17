"""Crops for the "is this a person down?" check that confirms the fall detector's boxes (person_down2.pt).

    python training/build_down_crops.py [--out data/down_verify]

The detector proposes, this check decides. So it learns from what the detector really gives:
  down      every labelled fallen person in data/fall_fyp train/valid, plus detector boxes that match one
            (IoU >= 0.5): the same person as the detector cuts them out
  not_down  detector boxes that match no fallen person (anything it wrongly fires on), on fall_fyp itself and
            on photos where nobody is down: Construction Site Safety train, Hard Hat Workers train and the
            hospital train photos; plus a share of the labelled upright people there (close-up workers are a
            known false alarm)
Splits: fall_fyp valid -> val, everything else -> train (10% of the negatives go to val). The test photos of
eval_down_confirm.py (fall_fyp test, CSS valid/test, HHW test, hospital test_colour) are never used.
Crops are cut with the same 20% margin as eval_down_confirm.confirmed(), saved as JPEG.
"""
import argparse
import glob
import json
import random
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
PAD = 0.2
DET_CONF = 0.15
PERSON_SHARE = 0.25   # of the labelled upright people on negative photos, this share is kept as not_down
NEGATIVE_SETS = {     # folder -> class id of "person" in its labels (None: no person labels used)
    "data/construction-site-safety/train": 5,
    "data/hard-hat-workers/train": None,
    "data/medical_ppe3/train": 0,
}


def iou(a, b):
    ix, iy = max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def labels(img_path, w, h, cls=None):
    lab = Path(str(img_path).replace("/images/", "/labels/")).with_suffix(".txt")
    out = []
    if lab.exists():
        for line in lab.read_text().splitlines():
            p = line.split()
            if len(p) < 5 or (cls is not None and int(p[0]) != cls):
                continue
            x, y, bw, bh = map(float, p[1:5])
            out.append([(x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h])
    return out


def crop(img, box):
    H, W = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = max(0, int(box[0] - PAD * bw)), max(0, int(box[1] - PAD * bh))
    x2, y2 = min(W, int(box[2] + PAD * bw)), min(H, int(box[3] + PAD * bh))
    c = img[y1:y2, x1:x2]
    return c if c.shape[0] >= 16 and c.shape[1] >= 16 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/down_verify")
    ap.add_argument("--detector", default="models/person_down2.pt")
    a = ap.parse_args()
    out, det = ROOT / a.out, YOLO(str(ROOT / a.detector))
    random.seed(0)
    n = {}

    def save(img, box, split, label, name):
        c = crop(img, box)
        if c is None:
            return
        d = out / split / label
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / f"{name}.jpg"), c, [cv2.IMWRITE_JPEG_QUALITY, 92])
        n[f"{split}/{label}"] = n.get(f"{split}/{label}", 0) + 1

    for split_in, split_out in (("train", "train"), ("valid", "val")):
        for i, p in enumerate(sorted(glob.glob(str(ROOT / f"data/fall_fyp/{split_in}/images/*")))):
            img = cv2.imread(p)
            if img is None:
                continue
            gts = labels(p, img.shape[1], img.shape[0])
            for j, g in enumerate(gts):
                save(img, g, split_out, "down", f"fall_{split_in}_{i}_gt{j}")
            r = det.predict(img, conf=DET_CONF, verbose=False)[0]
            for j, b in enumerate(r.boxes.xyxy.tolist()):
                best = max((iou(b, g) for g in gts), default=0)
                if best >= 0.5:
                    save(img, b, split_out, "down", f"fall_{split_in}_{i}_d{j}")
                elif best < 0.1:
                    save(img, b, split_out, "not_down", f"fall_{split_in}_{i}_fp{j}")

    for folder, person_cls in NEGATIVE_SETS.items():
        tag = Path(folder).parts[1]
        for i, p in enumerate(sorted(glob.glob(str(ROOT / folder / "images/*")))):
            if Path(p).name.startswith("grey_"):
                continue   # medical_ppe3's black-and-white copies of the same photos
            img = cv2.imread(p)
            if img is None:
                continue
            split = "val" if random.random() < 0.1 else "train"
            r = det.predict(img, conf=DET_CONF, verbose=False)[0]
            for j, b in enumerate(r.boxes.xyxy.tolist()):
                save(img, b, split, "not_down", f"{tag}_{i}_fp{j}")
            if person_cls is not None:
                for j, g in enumerate(labels(p, img.shape[1], img.shape[0], person_cls)):
                    if random.random() < PERSON_SHARE:
                        save(img, g, split, "not_down", f"{tag}_{i}_person{j}")

    (out / "build.json").write_text(json.dumps({"detector": a.detector, "det_conf": DET_CONF, "pad": PAD,
                                                "counts": n}, indent=2))
    print(json.dumps(n, indent=2))


if __name__ == "__main__":
    main()
