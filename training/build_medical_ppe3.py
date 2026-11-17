"""Hospital set v3: medical_ppe2 with the two problems behind weak gloves / goggles fixed as far as we can without
the original colour Biosafety photos.

    python training/build_medical_ppe3.py --base data/medical_ppe2 --out data/medical_ppe3 \
        --model outputs/runs/medical_ppe2_s/weights/best.pt

1. Missing labels. Many Biosafety photos show gloves / goggles nobody marked (checked by eye on the test split),
   so the model is punished for finding them. Boxes the given model is very sure of (>= FILL_CONF) are added
   when nothing of that class already overlaps them. Training photos only; test photos are never touched.
2. Colour. Every Biosafety photo is black-and-white (Roboflow "Grayscale" export) while CPPE-5 and real cameras are
   colour. Each colour training photo also goes in as a black-and-white copy, so colour stops telling the two
   sources apart and the model has to learn shapes.
3. Test. The CPPE-5 val (134) and test (29) photos, all colour, become test_colour/ and are not trained on.
   Model selection uses the Biosafety val split only.
"""
import argparse
import json
import os
from pathlib import Path

import cv2
from ultralytics import YOLO

NAMES = ["Person", "Coverall", "Face Shield", "Gloves", "Goggles", "Mask"]
FILL = {3: "Gloves", 4: "Goggles"}
FILL_CONF = 0.6
OVERLAP_IOU = 0.3


def iou(a, b):
    ax1, ay1, ax2, ay2 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1, bx2, by2 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw, ih = max(0, min(ax2, bx2) - max(ax1, bx1)), max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-9)


def read_labels(p: Path):
    if not p.exists():
        return []
    return [(int(l.split()[0]), [float(v) for v in l.split()[1:5]]) for l in p.read_text().splitlines() if l.strip()]


def write_labels(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"{c} {' '.join(f'{v:.6f}' for v in b)}\n" for c, b in rows))


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        os.link(src, dst)


def is_grey(img) -> bool:
    i = img.astype(int)
    return abs(i[..., 0] - i[..., 1]).mean() < 2 and abs(i[..., 1] - i[..., 2]).mean() < 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="data/medical_ppe2")
    ap.add_argument("--out", default="data/medical_ppe3")
    ap.add_argument("--model", default="outputs/runs/medical_ppe2_s/weights/best.pt")
    a = ap.parse_args()
    base, out = Path(a.base), Path(a.out)
    model = YOLO(a.model)
    stats = {"filled": {n: 0 for n in FILL.values()}, "grey_copies": 0, "train": 0, "val": 0, "test_colour": 0,
             "test_biosafety": 0}

    def copy_split(src_split, dst_split, names, fill: bool, grey_copies: bool):
        for img in names:
            lab = base / src_split / "labels" / (img.stem + ".txt")
            rows = read_labels(lab)
            if fill:
                res = model(str(img), verbose=False, conf=FILL_CONF)[0]
                for b in res.boxes:
                    c = int(b.cls[0])
                    if c in FILL:
                        box = b.xywhn[0].tolist()
                        if all(not (rc == c and iou(rb, box) > OVERLAP_IOU) for rc, rb in rows):
                            rows.append((c, box))
                            stats["filled"][FILL[c]] += 1
            link(img, out / dst_split / "images" / img.name)
            write_labels(out / dst_split / "labels" / (img.stem + ".txt"), rows)
            stats[dst_split] += 1
            if grey_copies:
                im = cv2.imread(str(img))
                if not is_grey(im):
                    g = cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                    cv2.imwrite(str(out / dst_split / "images" / f"grey_{img.stem}.jpg"), g, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    write_labels(out / dst_split / "labels" / f"grey_{img.stem}.txt", rows)
                    stats["grey_copies"] += 1

    imgs = lambda s: sorted((base / s / "images").iterdir())
    copy_split("train", "train", imgs("train"), fill=True, grey_copies=True)
    val = imgs("val")
    copy_split("val", "val", [p for p in val if p.name.startswith("bio_")], fill=True, grey_copies=False)
    copy_split("val", "test_colour", [p for p in val if not p.name.startswith("bio_")], fill=False, grey_copies=False)
    copy_split("test", "test_colour", imgs("test"), fill=False, grey_copies=False)
    copy_split("test_biosafety", "test_biosafety", imgs("test_biosafety"), fill=False, grey_copies=False)

    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(NAMES))
    (out / "data_local.yaml").write_text(f"path: {out.resolve()}\ntrain: train/images\nval: val/images\n"
                                         f"test: test_colour/images\nnames:\n{names}\n")
    (out / "build.json").write_text(json.dumps({"base": str(base), "fill_model": a.model, "fill_conf": FILL_CONF,
                                                **stats}, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
