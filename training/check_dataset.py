"""Check a YOLO-format dataset before training. Reads only, never changes the dataset.

Reports per split: image/label counts, images with no label file, empty label files
(background images), malformed label lines, class instance counts, class imbalance,
and identical images that appear in more than one split (train/test leakage).

    python training/check_dataset.py data/construction-ppe/data.yaml
    python training/check_dataset.py data/x/data.yaml --check-images   # also opens every image
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def resolve_root(data_yaml: Path, cfg: dict) -> Path:
    root = Path(cfg.get("path", "."))
    if not root.is_absolute():
        root = (data_yaml.parent / root) if (data_yaml.parent / root).exists() else data_yaml.parent
    return root.resolve()


def label_path(img: Path) -> Path:
    parts = list(img.parts)
    i = len(parts) - 1 - parts[::-1].index("images")  # last "images" folder
    parts[i] = "labels"
    return Path(*parts).with_suffix(".txt")


def check_split(img_dir: Path, n_classes: int, check_images: bool):
    images = sorted(p for p in img_dir.rglob("*") if p.suffix.lower() in IMG_EXT)
    r = {"images": len(images), "missing_label_file": [], "empty_label_file": 0,
         "bad_lines": [], "unreadable_images": [], "instances": Counter(), "images_per_class": Counter()}
    hashes = {}
    for img in images:
        hashes[hashlib.md5(img.read_bytes()).hexdigest()] = img
        if check_images:
            from PIL import Image
            try:
                with Image.open(img) as im:
                    im.verify()
            except Exception:
                r["unreadable_images"].append(str(img))

        lbl = label_path(img)
        if not lbl.exists():
            r["missing_label_file"].append(str(img))
            continue
        lines = [l for l in lbl.read_text().splitlines() if l.strip()]
        if not lines:
            r["empty_label_file"] += 1
            continue
        seen = set()
        for n, line in enumerate(lines, 1):
            v = line.split()
            problem = None
            try:
                if len(v) != 5:
                    raise IndexError
                cls, x, y, w, h = int(v[0]), *map(float, v[1:5])
                if not 0 <= cls < n_classes:
                    problem = f"class {cls} out of range"
                elif not all(0 <= c <= 1 for c in (x, y, w, h)) or w == 0 or h == 0:
                    problem = "coordinates outside 0-1 or zero size"
            except IndexError:
                problem = f"{len(v)} values (expected 5: class x y w h)"
            except ValueError:
                problem = "not numbers"
            if problem:
                r["bad_lines"].append(f"{lbl}:{n}: {problem}")
                continue
            r["instances"][cls] += 1
            seen.add(cls)
        for cls in seen:
            r["images_per_class"][cls] += 1
    return r, hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_yaml", type=Path)
    ap.add_argument("--check-images", action="store_true", help="open every image to find corrupt files (slow)")
    ap.add_argument("--out", type=Path, help="report path (default outputs/dataset_checks/<dataset>.json)")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.data_yaml.read_text())
    names = cfg["names"] if isinstance(cfg["names"], dict) else dict(enumerate(cfg["names"]))
    root = resolve_root(args.data_yaml, cfg)

    report = {"data_yaml": str(args.data_yaml.resolve()), "root": str(root), "classes": names, "splits": {}}
    split_hashes = {}
    for split in ("train", "val", "test"):
        if split not in cfg or not isinstance(cfg[split], str):
            continue
        img_dir = root / cfg[split]
        if not img_dir.is_dir():
            report["splits"][split] = {"error": f"folder not found: {img_dir}"}
            continue
        r, split_hashes[split] = check_split(img_dir, len(names), args.check_images)
        r["instances"] = {names[c]: r["instances"][c] for c in names}
        r["images_per_class"] = {names[c]: r["images_per_class"][c] for c in names}
        report["splits"][split] = r

    # identical images in more than one split
    leaks = defaultdict(list)
    for split, hashes in split_hashes.items():
        for h, img in hashes.items():
            leaks[h].append(f"{split}:{img.name}")
    report["duplicates_across_splits"] = [v for v in leaks.values() if len({s.split(':')[0] for s in v}) > 1]

    total = Counter()
    for r in report["splits"].values():
        total.update(r.get("instances", {}))
    nonzero = [v for v in total.values() if v]
    report["total_instances"] = dict(total)
    report["imbalance_ratio"] = round(max(nonzero) / min(nonzero), 1) if nonzero else None
    report["classes_with_no_instances"] = [n for n in names.values() if not total[n]]

    out = args.out or Path("outputs/dataset_checks") / f"{root.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    # summary
    print(f"Dataset: {root}")
    for split, r in report["splits"].items():
        if "error" in r:
            print(f"  {split:5}  ERROR {r['error']}")
            continue
        print(f"  {split:5}  {r['images']:6} images | no label file: {len(r['missing_label_file'])} | "
              f"empty (background): {r['empty_label_file']} | bad lines: {len(r['bad_lines'])}"
              + (f" | unreadable: {len(r['unreadable_images'])}" if args.check_images else ""))
    print("\n  Instances per class (all splits):")
    width = max(len(n) for n in names.values())
    for n in names.values():
        print(f"    {n:{width}}  {total[n]:7}")
    print(f"\n  Imbalance (most / least common class): {report['imbalance_ratio']}x")
    if report["classes_with_no_instances"]:
        print(f"  Classes with NO instances: {report['classes_with_no_instances']}")
    print(f"  Identical images in more than one split: {len(report['duplicates_across_splits'])}")
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
