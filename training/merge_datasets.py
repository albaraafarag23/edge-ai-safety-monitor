"""Merge an extra dataset into a base dataset, with a class mapping and auto-labels for missing classes.

The extra dataset's images are linked (not copied) and the source datasets are never changed.
Classes the extra dataset doesn't label (e.g. Person, vests, machinery in a helmet-only dataset) are
filled in by a trained model, so the merged training set doesn't teach "unlabeled person = background".

    python training/merge_datasets.py data/construction-site-safety/data_local.yaml data/hard-hat-workers \
        --map head=NO-Hardhat helmet=Hardhat --drop person \
        --autolabel outputs/runs/css_s_640/weights/best.pt --out data/css_hhw

Output: <out>/data.yaml with train/val = base + extra, test = base test only (so scores stay comparable),
plus test_extra = the extra dataset's test split. merge_report.json lists the counts.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = {"train": "train", "val": "valid", "test": "test"}


def load_names(names):
    return list(names.values()) if isinstance(names, dict) else list(names)


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        dst.symlink_to(src.resolve())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", type=Path, help="base dataset yaml (its class list is kept)")
    ap.add_argument("extra", type=Path, help="extra dataset folder (Roboflow YOLO export: train/valid/test)")
    ap.add_argument("--map", nargs="+", required=True, help="extra=base class pairs, e.g. head=NO-Hardhat")
    ap.add_argument("--drop", nargs="*", default=[], help="extra classes to discard")
    ap.add_argument("--autolabel", type=Path, help="weights that predict the base classes")
    ap.add_argument("--conf", type=float, default=0.5, help="auto-label confidence threshold")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    base_cfg = yaml.safe_load(args.base.read_text())
    base_root = Path(base_cfg["path"])
    base_names = load_names(base_cfg["names"])
    extra_names = load_names(yaml.safe_load((args.extra / "data.yaml").read_text())["names"])

    mapping = dict(pair.split("=", 1) for pair in args.map)
    for e, b in mapping.items():
        if e not in extra_names or b not in base_names:
            raise SystemExit(f"bad mapping {e}={b}: extra classes {extra_names}, base classes {base_names}")
    unknown = set(extra_names) - set(mapping) - set(args.drop)
    if unknown:
        raise SystemExit(f"extra classes neither mapped nor dropped: {sorted(unknown)}")
    remap = {extra_names.index(e): base_names.index(b) for e, b in mapping.items()}
    labeled_by_extra = set(remap.values())
    autolabel_ids = [i for i in range(len(base_names)) if i not in labeled_by_extra]

    model = None
    if args.autolabel:
        from ultralytics import YOLO
        model = YOLO(str(args.autolabel))
        if load_names(model.names) != base_names:
            raise SystemExit(f"auto-label model classes {load_names(model.names)} != base classes {base_names}")

    out = args.out.resolve()
    report = {"base": str(args.base), "extra": str(args.extra), "map": mapping, "drop": args.drop,
              "autolabel": str(args.autolabel) if model else None, "conf": args.conf, "splits": {}}

    for split, folder in SPLITS.items():
        counts = Counter()
        # base split: link images and labels as they are
        for img in sorted((base_root / folder / "images").iterdir()):
            if img.suffix.lower() not in IMG_EXT:
                continue
            target = "test" if split == "test" else split
            link(img, out / target / "images" / f"base_{img.name}")
            lbl = base_root / folder / "labels" / f"{img.stem}.txt"
            if lbl.exists():
                link(lbl, out / target / "labels" / f"base_{img.stem}.txt")
            counts["base_images"] += 1

        # extra split: remap labels and add auto-labels
        target = "test_extra" if split == "test" else split
        imgs = [p for p in sorted((args.extra / folder / "images").iterdir()) if p.suffix.lower() in IMG_EXT]
        for start in range(0, len(imgs), 32):
            chunk = imgs[start:start + 32]
            preds = model.predict([str(p) for p in chunk], conf=args.conf, classes=autolabel_ids,
                                  verbose=False) if model else [None] * len(chunk)
            for img, pred in zip(chunk, preds):
                lines = []
                lbl = args.extra / folder / "labels" / f"{img.stem}.txt"
                for line in (lbl.read_text().splitlines() if lbl.exists() else []):
                    parts = line.split()
                    if parts and int(parts[0]) in remap:
                        lines.append(" ".join([str(remap[int(parts[0])])] + parts[1:]))
                        counts[base_names[remap[int(parts[0])]]] += 1
                if pred is not None:
                    for c, box in zip(pred.boxes.cls.tolist(), pred.boxes.xywhn.tolist()):
                        lines.append(" ".join([str(int(c))] + [f"{v:.6f}" for v in box]))
                        counts[f"auto:{base_names[int(c)]}"] += 1
                link(img, out / target / "images" / f"extra_{img.name}")
                dst = out / target / "labels" / f"extra_{img.stem}.txt"
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text("\n".join(lines) + ("\n" if lines else ""))
                counts["extra_images"] += 1
        report["splits"][split] = dict(counts)
        print(split, dict(counts))

    (out / "data.yaml").write_text(yaml.safe_dump({
        "path": str(out), "train": "train/images", "val": "val/images", "test": "test/images",
        "test_extra": "test_extra/images", "names": base_names}, sort_keys=False))
    (out / "merge_report.json").write_text(json.dumps(report, indent=2))
    print(f"Wrote {out / 'data.yaml'}")


if __name__ == "__main__":
    main()
