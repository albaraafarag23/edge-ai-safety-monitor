"""Builds the hospital plugin's dataset from CPPE-5 (medical protective equipment: coverall, face shield, gloves,
goggles, mask; github.com/Rishit-dagli/CPPE-Dataset, code Apache-2.0, images collected from the web: research use).

CPPE-5 marks the equipment but not the people, and the detector needs both in one model (the rules check which
equipment is on which person). So people are added automatically: a large COCO model (yolo11x) marks them, and
only confident boxes are kept. The test split stays CPPE-5's own; validation is cut from its train split.

    python training/build_medical_ppe.py data/cppe5/raw --out data/medical_ppe
Needs train.parquet and test.parquet from huggingface.co/datasets/rishitdagli/cppe-5 (data/) in the raw folder.
"""
import argparse
import io
import json
import random
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image
from ultralytics import YOLO

NAMES = ["Person", "Coverall", "Face Shield", "Gloves", "Goggles", "Mask"]   # CPPE-5's order after Person
PERSON_CONF = 0.5
VAL_SHARE = 0.12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--person-model", default="yolo11x.pt")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    people = YOLO(args.person_model)
    rng = random.Random(args.seed)
    counts = {split: {n: 0 for n in NAMES} | {"images": 0} for split in ("train", "val", "test")}
    for source in ("train", "test"):
        rows = pq.read_table(args.raw / f"{source}.parquet").to_pylist()
        for row in rows:
            split = source if source == "test" else ("val" if rng.random() < VAL_SHARE else "train")
            image = Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB")
            w, h = image.size
            lines = []
            for (x, y, bw, bh), cat in zip(row["objects"]["bbox"], row["objects"]["category"]):
                bw, bh = min(bw, w - x), min(bh, h - y)
                if bw <= 1 or bh <= 1:
                    continue
                lines.append((cat + 1, (x + bw / 2) / w, (y + bh / 2) / h, bw / w, bh / h))
            found = people.predict(image, classes=[0], conf=PERSON_CONF, imgsz=960, verbose=False)[0]
            for cx, cy, bw, bh in found.boxes.xywhn.tolist():
                lines.append((0, cx, cy, bw, bh))
            stem = f"{source}_{row['image_id']:05d}"
            (args.out / "images" / split).mkdir(parents=True, exist_ok=True)
            (args.out / "labels" / split).mkdir(parents=True, exist_ok=True)
            image.save(args.out / "images" / split / f"{stem}.jpg", quality=92)
            (args.out / "labels" / split / f"{stem}.txt").write_text(
                "".join(f"{c} {a:.6f} {b:.6f} {cc:.6f} {d:.6f}\n" for c, a, b, cc, d in lines))
            counts[split]["images"] += 1
            for c, *_ in lines:
                counts[split][NAMES[c]] += 1
    (args.out / "data.yaml").write_text(
        f"path: {args.out.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(NAMES)))
    (args.out / "build.json").write_text(json.dumps(
        {"source": "CPPE-5", "person_labels": f"{args.person_model} at conf {PERSON_CONF}", "counts": counts}, indent=2))
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
