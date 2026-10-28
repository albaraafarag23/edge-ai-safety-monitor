"""Build the smoking-act dataset: person crops labelled smoking / holding / not_smoking (image classification).

    /home/albaraa/yoloenv/bin/python training/build_smoking_crops.py
    /home/albaraa/yoloenv/bin/python training/build_smoking_crops.py --out data/smoking_act2 --max-per-type 2000

"Smoking" means the act: the cigarette / vape / pipe at the mouth, or smoke coming out of it. Having one in the
hand is "holding", its own class, so the model learns that an item in the hand is not the act and the rule can
alert on smoking only.

Every source photo goes through a COCO pose model (person boxes plus nose, eyes, ears). For each person we cut
the region the live detector will cut at run time (upper_body_box: head and upper body, padded, made square) and
estimate where the mouth is (mouth_of). Then:
  - detection sets (item boxes): smoking if an item is within --at-mouth face widths of the mouth, or a smoke box
    starts at the mouth; holding if the nearest item is at least --in-hand face widths away; in between: left out.
    Holding is only trusted from sets that label smoke: elsewhere someone breathing out a cloud with the vape back
    in their hand looks like holding, so those crops go to unsure/ (see below).
    A person must face the camera roughly upright (upside-down / sideways copies give wrong points).
  - classification sets that only say "smoking" for the whole photo (Mendeley, cigar/pipe/shisha, Stanford 40
    "smoking"): no item box, so mouth or hand can't be told apart. Those crops go to <out>/unsure/ for a second
    step (training/sort_unsure.py) and are not trained on until sorted.
  - not_smoking only from sources that say so: look-alikes (Stanford 40 drinking, phoning, brushing teeth,
    blowing bubbles, make-up, texting, taking photos; the Mendeley and cigar/pipe/shisha look-alikes), ordinary
    people, and construction workers. People in smoking photos with no item near them are not used: their labels
    may simply be missing.

Sets that aren't downloaded yet are skipped. Source folders are never changed. Of the copies Roboflow made of one
photo (rotated, flipped), the copy where the person is found most clearly is used. Splits (80/10/10) are made per
original photo; crops that are exact duplicates (same image hash) are kept once.

Output: <out>/{train,val,test}/{smoking,holding,not_smoking}/*.jpg (Ultralytics classify layout), <out>/unsure/,
<out>/manifest.csv (label, type, source, licence, original photo, box, mouth distance) and
outputs/dataset_checks/<out name>/build_summary.json plus a sample sheet per label and type.
"""
import argparse
import csv
import hashlib
import json
import math
import random
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CROP_SIZE = 256
LABELS = ("smoking", "holding", "not_smoking")
# Source class name (lower case) -> smoking type. "smoke" boxes count separately (breathing smoke out).
TYPE_OF = {"cigarette": "cigarette", "vape": "vape", "pipe": "pipe", "cigar": "cigar", "hookah": "shisha",
           "hookah-detect": "shisha", "shisha_hookah": "shisha", "smoking": "unspecified"}
SMOKE = {"smoke"}
# Stanford 40 actions that look like smoking from a distance (hand or object at the face).
LOOKALIKES = {"drinking", "phoning", "brushing_teeth", "blowing_bubbles", "applying_cosmetics", "texting_message",
              "taking_photos"}

CC = "CC BY 4.0"
# name, kind, folder, licence. kind: det = item boxes, cls = whole-photo label, css = construction workers,
# stanford = Stanford 40 Actions (action per photo, box of the person doing it).
SOURCES = [
    ("cig_vape_5k", "det", "data/smk_cig_vape_5k", CC + ", Roboflow hugefissure/cigarette-vape-detection-lagrc v1"),
    ("stelar", "det", "data/smk_stelar_vape_cig", CC + ", Roboflow stelar/vape-cigarette-detection-2 v2"),
    ("miprivado", "det", "data/smk_miprivado_17k", "MIT, Roboflow mi-privado/cigarette-detection-iggcm (fork)"),
    ("smoketrack", "det", "data/smk_smoketrack", CC + ", Roboflow smoketrack/smoketrack-eldf7 v3"),
    ("vnf3r", "det", "data/smk_vnf3r", CC + ", Roboflow object-detection-vnf3r/smoking-qbqdv v1"),
    ("cigdet", "det", "data/cigdet/yolo", CC + ", CigDet, Mendeley doi:10.17632/6hyrr8typ7.1"),
    ("cps_v3", "cls", "data/smk_cigar_pipe_shisha_cls_v3", CC + ", Roboflow object-detection-trurj/cigar-pipe-shisha-classification v3"),
    ("cps_v4", "cls", "data/smk_cigar_pipe_shisha_cls", CC + ", Roboflow object-detection-trurj/cigar-pipe-shisha-classification v4"),
    ("mendeley_1120", "cls", "data/smk_mendeley_smoker_1120", CC + ", Mendeley doi:10.17632/j45dj8bgfc.1"),
    ("mendeley_2400", "cls", "data/smk_mendeley_smoking_2400", CC + ", Mendeley doi:10.17632/7b52hhzs3r.1"),
    ("stanford40", "stanford", "data/stanford40", "Research use, cite Yao et al. ICCV 2011 (Stanford 40 Actions); not for republishing"),
    ("css_workers", "css", "data/construction-site-safety", CC + ", Roboflow Construction Site Safety v28"),
]
# Downloaded but not used: smk_hookah_detect and smk_hookah_sava are shop photos of hookahs (no people);
# smk_pipe_newsmoke is industrial pipes and smoke, not smoking pipes.


def upper_body_box(person, img_w, img_h, pad=0.1):
    """Head and upper body of a person box (x1, y1, x2, y2), padded and made square. May extend past the image.

    Standing person (tall box): the top half. Half-body or close-up: most or all of the box. The live detector
    must cut the same region from its Person boxes, so keep this in step with cv_pipeline.
    """
    x1, y1, x2, y2 = person
    w, h = x2 - x1, y2 - y1
    h = min(h, max(0.5 * h, 1.2 * w))
    side = max(w, h) * (1 + 2 * pad)
    cx, cy = (x1 + x2) / 2, y1 + h / 2
    return cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2


def mouth_of(kpts, conf, min_conf=0.5):
    """(mouth point, face width) from COCO pose points (0 nose, 1-2 eyes, 3-4 ears), or None.

    None when the nose or both eyes are missing, or the face isn't roughly upright (eyes not above the nose):
    rotated copies give points that can't be trusted. The mouth sits below the nose by ~1.25x eyes-to-nose.
    """
    nose, eyes = kpts[0], [kpts[i] for i in (1, 2) if conf[i] >= min_conf]
    if conf[0] < min_conf or not eyes:
        return None
    down = nose - np.mean(eyes, axis=0)
    if np.linalg.norm(down) < 1 or down[1] <= 0 or abs(down[0]) > 1.2 * down[1]:
        return None
    if len(eyes) == 2:
        size = max(np.linalg.norm(kpts[1] - kpts[2]), 1.6 * np.linalg.norm(down))
    else:
        size = 2.2 * np.linalg.norm(down)
        ears = [kpts[i] for i in (3, 4) if conf[i] >= min_conf]
        if ears:
            size = max(size, 0.9 * np.linalg.norm(ears[0] - nose))
    return nose + 1.25 * down, float(size)


def gap_to_box(p, box):
    """Distance from a point to a box (0 inside)."""
    return math.hypot(max(box[0] - p[0], 0, p[0] - box[2]), max(box[1] - p[1], 0, p[1] - box[3]))


def cut(img, box, size=CROP_SIZE):
    """Crop a box that may extend past the image, filling the outside with grey (114, as YOLO letterboxing)."""
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    h, w = img.shape[:2]
    out = np.full((y2 - y1, x2 - x1, 3), 114, np.uint8)
    sx1, sy1, sx2, sy2 = max(x1, 0), max(y1, 0), min(x2, w), min(y2, h)
    if sx2 > sx1 and sy2 > sy1:
        out[sy1 - y1:sy2 - y1, sx1 - x1:sx2 - x1] = img[sy1:sy2, sx1:sx2]
    return cv2.resize(out, (size, size), interpolation=cv2.INTER_AREA)


def ioa(obj, region):
    """Share of the object box that lies inside region."""
    ix = max(0, min(obj[2], region[2]) - max(obj[0], region[0]))
    iy = max(0, min(obj[3], region[3]) - max(obj[1], region[1]))
    area = (obj[2] - obj[0]) * (obj[3] - obj[1])
    return ix * iy / area if area > 0 else 0


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0


def dhash(img):
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    return np.packbits((g[:, 1:] > g[:, :-1]).flatten()).tobytes().hex()


def group_key(path):
    """Original photo name: Roboflow exports name copies '<orig>_jpg.rf.<hash>.jpg'."""
    stem = path.stem.split(".rf.")[0].lower()
    for ext in ("_jpg", "_jpeg", "_png", "_webp"):
        stem = stem.removesuffix(ext)
    return stem


def split_of(key, val=0.1, test=0.1):
    r = int(hashlib.md5(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if r < test else "val" if r < test + val else "train"


def images_under(folder):
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMG_EXT)


def label_of(img):
    """YOLO label file for an image: the last 'images' folder in its path becomes 'labels'."""
    parts = list(img.parts)
    i = len(parts) - 1 - parts[::-1].index("images")
    return Path(*parts[:i], "labels", *parts[i + 1:]).with_suffix(".txt")


def yolo_boxes(label_path, w, h):
    """YOLO boxes (or segmentation polygons, turned into boxes) -> [(class, (x1, y1, x2, y2))] in pixels."""
    out = []
    if not label_path.exists():
        return out
    for line in label_path.read_text().splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        c, v = int(p[0]), list(map(float, p[1:]))
        if len(v) == 4:
            x, y, bw, bh = v
            box = ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)
        else:
            xs, ys = v[0::2], v[1::2]
            box = (min(xs) * w, min(ys) * h, max(xs) * w, max(ys) * h)
        out.append((c, box))
    return out


def class_names(folder):
    for f in (folder / "data.yaml", folder / "data_local.yaml"):
        if f.exists():
            n = yaml.safe_load(f.read_text())["names"]
            return [s.lower() for s in (n.values() if isinstance(n, dict) else n)]
    raise SystemExit(f"no data.yaml in {folder}")


def stanford_box(folder, img):
    """Box of the person doing the action, from Stanford 40's XML annotation."""
    xml = folder / "XMLAnnotations" / (img.stem + ".xml")
    if not xml.exists():
        return None
    b = ET.parse(xml).getroot().find(".//bndbox")
    return tuple(float(b.find(k).text) for k in ("xmin", "ymin", "xmax", "ymax")) if b is not None else None


def photo_items(name, kind, folder):
    """Yield (image path, whole-photo label or None, type) for one source (every copy of every photo)."""
    for img in images_under(folder):
        if kind == "stanford":
            if img.parent.name != "JPEGImages":
                continue
            action = img.stem.rsplit("_", 1)[0]
            if action == "smoking":
                yield img, "unsure", "unspecified"
            else:
                yield img, "not_smoking", ("lookalike_" + action) if action in LOOKALIKES else "general_stanford"
        elif kind == "cls":
            parts = [s.lower() for s in img.relative_to(folder).parts[:-1]] + [img.stem.lower()]
            if name.startswith("mendeley"):
                if "testing_data" in parts:  # 2400 set: its test photos carry no label
                    continue
                smoking = not any(s.startswith("notsmoking") for s in parts) and \
                    any(s.startswith("smoking") for s in parts)
                not_smoking = any(s.startswith("notsmoking") for s in parts)
                if smoking:
                    yield img, "unsure", "unspecified"
                elif not_smoking:  # the 1,120 set picked look-alikes on purpose
                    yield img, "not_smoking", "lookalike_mendeley" if name == "mendeley_1120" else "general_mendeley"
            else:
                cls = parts[-2]
                if cls == "normal":
                    yield img, "not_smoking", "lookalike_cps"
                elif cls in TYPE_OF:
                    yield img, "unsure", TYPE_OF[cls]
        elif kind == "css":
            yield img, "not_smoking", "worker"
        else:
            yield img, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/smoking_act2"))
    ap.add_argument("--person-model", default="yolo11s-pose.pt",
                    help="COCO pose model: person boxes plus nose / eye / ear points")
    ap.add_argument("--person-conf", type=float, default=0.35)
    ap.add_argument("--min-person", type=int, default=48, help="skip people smaller than this (px, box height)")
    ap.add_argument("--in-crop", type=float, default=0.5, help="share of an item box that must be in the person's crop")
    ap.add_argument("--at-mouth", type=float, default=0.25, help="item this close to the mouth (face widths): smoking")
    ap.add_argument("--smoke-at-mouth", type=float, default=0.5, help="smoke box this close to the mouth: smoking")
    ap.add_argument("--in-hand", type=float, default=0.8, help="nearest item at least this far from the mouth: holding")
    ap.add_argument("--max-per-type", type=int, default=2000, help="cap per label and item type")
    ap.add_argument("--max-css", type=int, default=3000, help="construction-worker crops (not smoking)")
    ap.add_argument("--max-stanford-general", type=int, default=1500,
                    help="Stanford 40 crops of other everyday actions (not smoking, not look-alikes)")
    ap.add_argument("--max-per-source", type=int, nargs="*", default=["stelar=400"],
                    help="name=n caps, e.g. stelar=400 (a few video clips of the same people)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.out.exists():
        raise SystemExit(f"{args.out} already exists; remove it or pick another --out")
    from ultralytics import YOLO
    detector = YOLO(args.person_model)
    rng = random.Random(args.seed)
    source_caps = dict((s.split("=")[0], int(s.split("=")[1])) for s in args.max_per_source)

    rows, skipped, hashes = [], Counter(), set()
    for name, kind, folder, licence in SOURCES:
        folder = Path(folder)
        if not folder.exists() or (folder / "roboflow.zip").exists() or \
                kind in ("det", "css") and not any((folder / f).exists() for f in ("data.yaml", "data_local.yaml")) or \
                kind == "stanford" and not (folder / "XMLAnnotations").exists():
            print(f"[skip] {name}: {folder} not downloaded (or still downloading)")
            skipped[f"{name}: not downloaded"] += 1
            continue
        names = class_names(folder) if kind in ("det", "css") else None
        items = list(photo_items(name, kind, folder))
        rng.shuffle(items)
        found = defaultdict(list)  # group -> [(copy score, path, entries)]
        for i in range(0, len(items), 32):
            chunk = items[i:i + 32]
            imgs = [cv2.imread(str(p)) for p, _, _ in chunk]
            if kind != "css":
                preds = iter(detector.predict([im for im in imgs if im is not None], classes=[0],
                                              conf=args.person_conf, verbose=False))
            for (path, label, ptype), img in zip(chunk, imgs):
                if img is None:
                    skipped["unreadable image"] += 1
                    continue
                h, w = img.shape[:2]
                if kind == "css":
                    people = [dict(box=b, conf=1.0, mouth=None) for c, b in yolo_boxes(label_of(path), w, h)
                              if names[c] == "person"]
                else:
                    r = next(preds)
                    k = r.keypoints.xy.cpu().numpy() if r.keypoints is not None else None
                    kc = r.keypoints.conf.cpu().numpy() if r.keypoints is not None and r.keypoints.conf is not None else None
                    people = [dict(box=tuple(b), conf=float(cf),
                                   mouth=mouth_of(k[j], kc[j]) if kc is not None else None)
                              for j, (b, cf) in enumerate(zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()))]
                people = [p for p in people if p["box"][3] - p["box"][1] >= args.min_person]
                entries, why = [], Counter()  # entry: (label, type, region, person conf, mouth distance)
                if kind == "css":
                    entries = [("not_smoking", ptype, upper_body_box(p["box"], w, h), 1.0, None) for p in people]
                elif kind in ("cls", "stanford"):
                    if kind == "stanford":
                        ref = stanford_box(folder, path)
                        cand = [p for p in people if ref and iou(p["box"], ref) >= 0.3]
                        pick = max(cand, key=lambda p: iou(p["box"], ref)) if cand else None
                        if pick is None:
                            why["Stanford person not found by the pose model"] += 1
                    else:
                        pick = max(people, key=lambda p: (p["box"][2] - p["box"][0]) * (p["box"][3] - p["box"][1]),
                                   default=None)
                        if pick is None:
                            why["no person found"] += 1
                    if pick is not None:
                        if label == "unsure" and pick["mouth"] is None:
                            why["smoking photo, face not visible or not upright"] += 1
                        else:
                            entries.append((label, ptype, upper_body_box(pick["box"], w, h), pick["conf"], None))
                else:
                    lab = yolo_boxes(label_of(path), w, h)
                    objs = [(TYPE_OF[names[c]], b) for c, b in lab if names[c] in TYPE_OF]
                    smoke = [b for c, b in lab if names[c] in SMOKE]
                    if not people:
                        why["no person found (object close-up or product photo)"] += 1
                    regions = [upper_body_box(p["box"], w, h) for p in people]
                    owner = defaultdict(list)
                    for t, ob in objs:
                        if not regions:
                            break
                        best = max(range(len(regions)), key=lambda j: ioa(ob, regions[j]))
                        if ioa(ob, regions[best]) >= args.in_crop:
                            owner[best].append((t, ob))
                        else:
                            why["item not near any person"] += 1
                    for j, p in enumerate(people):
                        if not owner[j]:
                            why["person with no item near them (not used)"] += 1
                            continue
                        if p["mouth"] is None:
                            why["person with item, face not visible or not upright"] += 1
                            continue
                        mp, size = p["mouth"]
                        named = [o for o in owner[j] if o[0] != "unspecified"] or owner[j]
                        d_item = min(gap_to_box(mp, b) / size for _, b in named)
                        d_smoke = min((gap_to_box(mp, b) / size for b in smoke), default=99)
                        t = min(named, key=lambda o: gap_to_box(mp, o[1]))[0]
                        if d_item <= args.at_mouth or d_smoke <= args.smoke_at_mouth:
                            entries.append(("smoking", t, regions[j], p["conf"], round(min(d_item, d_smoke), 3)))
                        elif d_item >= args.in_hand:
                            sure = t != "unspecified" and any(n in SMOKE for n in names)
                            entries.append(("holding" if sure else "unsure", t, regions[j], p["conf"], round(d_item, 3)))
                        else:
                            why["item between mouth and hand (unclear, not used)"] += 1
                score = max((p["conf"] for p in people if p["mouth"] is not None or kind == "css"), default=0)
                found[group_key(path)].append((score + len(entries), path, entries, why))

        # Of each photo's copies, keep the clearest one (most crops, then most confident person).
        n_crops = 0
        for key, copies in found.items():
            score, path, entries, why = max(copies, key=lambda c: c[0])
            skipped.update({f"{name}: {k}": v for k, v in why.items()})
            if len(copies) > 1:
                skipped[f"{name}: rotated / flipped copies dropped"] += len(copies) - 1
            for label, ptype, region, cf, d in entries:
                rows.append(dict(source=name, licence=licence, src_image=str(path), group=key, label=label,
                                 type=ptype, box=[round(v, 1) for v in region], person_conf=round(cf, 3),
                                 mouth_dist=d))
                n_crops += 1
        print(f"[{name}] {len(items)} photos ({len(found)} originals) -> {n_crops} crops")

    # Caps, after shuffling across sources.
    rng.shuffle(rows)
    def cap_of(r):
        if r["source"] in source_caps and r["label"] != "not_smoking":
            return (r["source"],), source_caps[r["source"]]
        if r["source"] == "css_workers":
            return ("css_workers",), args.max_css
        if r["type"] == "general_stanford":
            return ("general_stanford",), args.max_stanford_general
        if r["label"] in ("smoking", "holding"):
            return (r["label"], r["type"]), args.max_per_type
        return None, None

    caps, kept = Counter(), []
    for r in rows:
        key, limit = cap_of(r)
        caps[key] += 1
        if limit and caps[key] > limit:
            skipped[f"{'/'.join(key)}: over the cap of {limit}"] += 1
            continue
        kept.append(r)

    # Write crops; exact-duplicate crops are kept once. Unsure crops go to <out>/unsure/ (not a split).
    counts = Counter()
    for i, r in enumerate(kept):
        crop = cut(cv2.imread(r["src_image"]), r["box"])
        hsh = dhash(crop)
        if hsh in hashes:
            skipped["duplicate crop"] += 1
            r["crop"] = None
            continue
        hashes.add(hsh)
        r["split"] = "unsure" if r["label"] == "unsure" else split_of(r["group"])
        sub = Path("unsure") if r["label"] == "unsure" else Path(r["split"]) / r["label"]
        out = args.out / sub / f"{r['source']}_{r['type']}_{i:06d}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        r["crop"] = str(out.relative_to(args.out))
        counts[(r["split"], r["label"], r["type"])] += 1
    kept = [r for r in kept if r["crop"]]

    with open(args.out / "manifest.csv", "w", newline="") as f:
        cols = ["crop", "split", "label", "type", "source", "licence", "src_image", "group", "box", "person_conf",
                "mouth_dist"]
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(kept)

    report_dir = Path("outputs/dataset_checks") / args.out.name
    report_dir.mkdir(parents=True, exist_ok=True)
    table = defaultdict(Counter)
    for (split, label, ptype), n in counts.items():
        table[f"{label}/{ptype}"][split] += n
    summary = {
        "out": str(args.out), "settings": {k: str(v) for k, v in vars(args).items()},
        "by_label_and_type": {k: dict(v, total=sum(v.values())) for k, v in sorted(table.items())},
        "by_source": dict(Counter(r["source"] for r in kept)),
        "by_split": dict(Counter((r["split"] + "/" + r["label"]) for r in kept)),
        "skipped": dict(sorted(skipped.items())),
    }
    (report_dir / "build_summary.json").write_text(json.dumps(summary, indent=2))

    # One sample sheet per label and type, to check the crops by eye.
    by_group = defaultdict(list)
    for r in kept:
        by_group[f"{r['label']}_{r['type']}"].append(r)
    for g, rs in by_group.items():
        pick = rng.sample(rs, min(30, len(rs)))
        tiles = [cv2.resize(cv2.imread(str(args.out / r["crop"])), (160, 160)) for r in pick]
        tiles += [np.full((160, 160, 3), 255, np.uint8)] * (-len(tiles) % 10)
        sheet = np.vstack([np.hstack(tiles[k:k + 10]) for k in range(0, len(tiles), 10)])
        cv2.imwrite(str(report_dir / f"sheet_{g}.jpg"), sheet)

    print(json.dumps({k: summary[k] for k in ("by_label_and_type", "by_split")}, indent=2))
    print(f"Saved to {args.out}. Summary: {report_dir / 'build_summary.json'}")


if __name__ == "__main__":
    main()
