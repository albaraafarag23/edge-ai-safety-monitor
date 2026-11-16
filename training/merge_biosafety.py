"""Adds the Biosafety PPE set (Roboflow defect-detection-ttidk/biosafety-ppe-detection-u2ha2 v1, CC BY 4.0: masks,
goggles, face shields, gloves) to the hospital set, for the two rules switched off for weak recall: gloves and eye
protection.

    python training/merge_biosafety.py --base data/medical_ppe --extra data/mppe_biosafety --out data/medical_ppe2

- Names mapped to ours; "lab coat", "hair net" and "shoe cover" are dropped (a lab coat is not an isolation gown:
  it must not teach the model that it is).
- People, which the extra set never marks, are filled in automatically (yolo11x, COCO), as build_medical_ppe.py
  did for CPPE-5. Gowns are NOT filled in: the extra set labels lab coats, so an unmarked coat there really isn't a
  gown (an earlier try let the hospital model mark 1,001 "gowns" in it, mostly lab coats).
- Each source keeps its own test pictures (test/ = CPPE-5, test_biosafety/ = the new set) so old and new models
  can be compared on both. Images are hard-linked, not copied.
"""
import argparse
import json
import os
import shutil
from pathlib import Path

from ultralytics import YOLO

NAMES = ["Person", "Coverall", "Face Shield", "Gloves", "Goggles", "Mask"]
EXTRA_TO_OURS = {"face shield": "Face Shield", "gloves": "Gloves", "goggles": "Goggles", "mask": "Mask"}
PERSON_CONF = 0.5
SPLITS = {"train": "train", "valid": "val", "test": "test_biosafety"}


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        os.link(src, dst)


def boxes_of(result, keep: dict[int, float]) -> list[tuple[int, list[float]]]:
    out = []
    for b in result.boxes:
        cls, conf = int(b.cls[0]), float(b.conf[0])
        if cls in keep and conf >= keep[cls]:
            out.append((cls, b.xywhn[0].tolist()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--extra", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--person-model", default="yolo11x.pt")
    args = ap.parse_args()

    # 1. the existing set, as it is (either layout: <split>/images or images/<split>)
    for split in ("train", "val", "test"):
        images = args.base / split / "images"
        labels = args.base / split / "labels"
        if not images.is_dir():
            images, labels = args.base / "images" / split, args.base / "labels" / split
        found = sorted(images.glob("*"))
        if not found:
            raise SystemExit(f"no {split} images in {args.base}")
        for img in found:
            link(img, args.out / split / "images" / img.name)
            label = labels / (img.stem + ".txt")
            if label.exists():
                link(label, args.out / split / "labels" / label.name)

    # 2. the extra set, mapped and filled in
    extra_names = __import__("yaml").safe_load(open(args.extra / "data.yaml"))["names"]
    people = YOLO(args.person_model)
    counts = {}
    for src_split, split in SPLITS.items():
        c = counts.setdefault(split, {n: 0 for n in NAMES} | {"images": 0, "dropped_boxes": 0})
        for img in sorted((args.extra / src_split / "images").glob("*")):
            lines = []
            label = args.extra / src_split / "labels" / (img.stem + ".txt")
            for row in (label.read_text().split("\n") if label.exists() else []):
                parts = row.split()
                if len(parts) != 5:
                    continue
                ours = EXTRA_TO_OURS.get(extra_names[int(parts[0])])
                if ours is None:
                    c["dropped_boxes"] += 1
                    continue
                lines.append(f"{NAMES.index(ours)} {' '.join(parts[1:])}")
                c[ours] += 1
            for _, xywh in boxes_of(people.predict(str(img), verbose=False)[0], {0: PERSON_CONF}):
                lines.append(f"{NAMES.index('Person')} " + " ".join(f"{v:.6f}" for v in xywh))
                c["Person"] += 1
            name = f"bio_{img.name}"
            link(img, args.out / split / "images" / name)
            (args.out / split / "labels").mkdir(parents=True, exist_ok=True)
            (args.out / split / "labels" / f"bio_{img.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            c["images"] += 1

    root = args.out.resolve()
    (args.out / "data_local.yaml").write_text(
        f"path: {root}\ntrain: train/images\nval: val/images\ntest: test/images\nnc: {len(NAMES)}\nnames: {NAMES}\n")
    (args.out / "data_test_biosafety.yaml").write_text(
        f"path: {root}\ntrain: train/images\nval: test_biosafety/images\nnc: {len(NAMES)}\nnames: {NAMES}\n")
    shutil.copy(args.extra / "README.dataset.txt", args.out / "README.biosafety.txt")
    (args.out / "build.json").write_text(json.dumps({"added": counts, "person_conf": PERSON_CONF}, indent=2))
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
