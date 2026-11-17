"""Crops of people labelled by posture (lie / sit / bend / stand) for the "lying or not?" checks.

    python training/build_posture_crops.py [--out data/posture_crops]

Sources (both CC BY 4.0, Roboflow):
  data/fall_posture_dqhnv  fall-detection-xmfkt/fall-detection-dqhnv v4: bend / lie / sit / stand, a high indoor
                           camera like a site box. Exported stretched to 640x640 (every version is).
  data/fall_posture_lutcc  fall-detect-cgumc/fall-detection-lutcc v1: Lying-Down / Sitting / Standing / Walking.
Many dqhnv pictures are frames of the same few clips (and copies of one frame), so they are split by blocks of
frame numbers (BLOCK frames per block), never frame by frame: neighbouring frames stay on one side.
Crops get the same 20% margin as the live check (training/eval_down_confirm.py).
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
PAD = 0.2
BLOCK = 25
VAL_SHARE = 0.15
SOURCES = {
    "data/fall_posture_dqhnv": {"bend": "bend", "lie": "lie", "sit": "sit", "stand": "stand"},
    "data/fall_posture_lutcc": {"Lying-Down": "lie", "Sitting": "sit", "Standing": "stand", "Walking": "stand"},
}


def group_of(name: str) -> str:
    """Frame group: the file name before Roboflow's '.rf.' suffix, frame number in blocks of BLOCK."""
    stem = name.split(".rf.")[0]
    m = re.match(r"^(.*?)(\d+)(_[a-z]+)?$", stem)
    return f"{m.group(1)}{int(m.group(2)) // BLOCK}" if m else stem


def split_of(source: str, name: str) -> str:
    h = int(hashlib.sha1(f"{source}/{group_of(name)}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "val" if h < VAL_SHARE else "train"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/posture_crops")
    a = ap.parse_args()
    out = ROOT / a.out
    counts = {}
    for source, mapping in SOURCES.items():
        src = ROOT / source
        names = None
        for line in (src / "data.yaml").read_text().splitlines():
            if line.startswith("names:"):
                names = json.loads(line.split(":", 1)[1].replace("'", '"'))
        for img_path in sorted(src.glob("*/images/*")):
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            H, W = img.shape[:2]
            split = split_of(source, img_path.name)
            lab = img_path.parent.parent / "labels" / (img_path.stem + ".txt")
            if not lab.exists():
                continue
            for j, line in enumerate(lab.read_text().split("\n")):
                p = line.split()
                if len(p) != 5:
                    continue   # polygons or empty lines
                label = mapping.get(names[int(p[0])])
                if not label:
                    continue
                x, y, bw, bh = (float(v) for v in p[1:5])
                x1, y1 = max(0, int((x - bw / 2 - PAD * bw) * W)), max(0, int((y - bh / 2 - PAD * bh) * H))
                x2, y2 = min(W, int((x + bw / 2 + PAD * bw) * W)), min(H, int((y + bh / 2 + PAD * bh) * H))
                crop = img[y1:y2, x1:x2]
                if crop.shape[0] < 16 or crop.shape[1] < 16:
                    continue
                d = out / split / label
                d.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(d / f"{Path(source).name}_{img_path.stem[:60]}_{j}.jpg"), crop,
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
                counts[f"{split}/{label}"] = counts.get(f"{split}/{label}", 0) + 1
    (out / "build.json").write_text(json.dumps({"sources": list(SOURCES), "pad": PAD, "block": BLOCK,
                                                "counts": counts}, indent=2))
    print(json.dumps(dict(sorted(counts.items())), indent=2))


if __name__ == "__main__":
    main()
