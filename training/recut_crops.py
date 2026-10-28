"""Re-cut a built smoking-act dataset at another crop size, from the original photos and the boxes in its
manifest (no person detection, so it takes minutes instead of a full rebuild).

    python training/recut_crops.py data/smoking_act2 data/smoking_act2_384 --size 384

Same splits, labels and file names; unsure crops are left out. The manifest is copied with the new crop paths.
"""
import argparse
import csv
import json
from pathlib import Path

import cv2

from build_smoking_crops import cut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--size", type=int, default=384)
    args = ap.parse_args()
    if args.dst.exists():
        raise SystemExit(f"{args.dst} already exists")

    rows = [r for r in csv.DictReader(open(args.src / "manifest.csv")) if r["split"] in ("train", "val", "test")]
    for i, r in enumerate(rows):
        out = args.dst / r["crop"]
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), cut(cv2.imread(r["src_image"]), json.loads(r["box"]), args.size),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        if i % 2000 == 0:
            print(f"{i}/{len(rows)}")
    with open(args.dst / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} crops at {args.size}px to {args.dst}")


if __name__ == "__main__":
    main()
