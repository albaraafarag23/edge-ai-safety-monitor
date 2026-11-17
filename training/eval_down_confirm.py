"""Person down, second try: the fall detector proposes, a pose model on the turned-around patch confirms.

The pose rule (cv_pipeline/posture.py) misses most falls because pose models hardly ever find a body lying flat:
they learned from people standing. Turned 90 degrees, a lying body looks like a standing one. So: every box the
fall detector (person_down2.pt) gives is cut out with a margin, the pose model looks at it as it is and turned
90 degrees both ways, the body points are turned back, and the box only counts if a body is found whose torso
lies along the ground (posture.is_lying). A truck, a railing or a wall has no shoulders and hips.

    python training/eval_down_confirm.py [--detector models/person_down2.pt] [--pose models/yolo11n-pose.pt]

Measures, for each detector confidence:
  falls caught   the 422 fallen people in data/fall_fyp/test (box overlap >= 0.3); about a third of them sit
                 rather than lie, which the rule leaves alone on purpose (workers sit to rest)
  false alarms   photos with nobody down: Construction Site Safety valid + test, Hard Hat Workers test,
                 hospital colour test (people standing, working, close up); counted per photo
Writes outputs/eval/down_confirm.json.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cv_pipeline"))
sys.path.insert(0, str(ROOT / "training"))
from posture import is_lying  # noqa: E402

PAD = 0.2
NEGATIVES = ["data/construction-site-safety/valid/images", "data/construction-site-safety/test/images",
             "data/hard-hat-workers/test/images", "data/medical_ppe3/test_colour/images"]


def iou(a, b):
    ix, iy = max(0, min(a[2], b[2]) - max(a[0], b[0])), max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def turned_back(kps, turn, w, h):
    """Body points found on the turned patch, in the patch's own (unturned) pixels. w, h: unturned size."""
    out = []
    for x, y, c in kps:
        if turn == cv2.ROTATE_90_CLOCKWISE:            # (x, y) -> (h-1-y, x)
            out.append([y, h - 1 - x, c])
        elif turn == cv2.ROTATE_90_COUNTERCLOCKWISE:   # (x, y) -> (y, w-1-x)
            out.append([w - 1 - y, x, c])
        else:
            out.append([x, y, c])
    return out


def confirmed(img, box, pose, pose_conf=0.3, min_cover=0.3):
    """Is there a body lying along the ground inside this box?"""
    H, W = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = max(0, int(box[0] - PAD * bw)), max(0, int(box[1] - PAD * bh))
    x2, y2 = min(W, int(box[2] + PAD * bw)), min(H, int(box[3] + PAD * bh))
    patch = img[y1:y2, x1:x2]
    h, w = patch.shape[:2]
    if w < 16 or h < 16:
        return False
    turns = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE]
    views = [patch if t is None else cv2.rotate(patch, t) for t in turns]
    for t, r in zip(turns, pose.predict(views, conf=pose_conf, verbose=False)):
        for b, k in zip(r.boxes.xyxy.tolist(), r.keypoints.data.tolist()):
            if (b[2] - b[0]) * (b[3] - b[1]) < min_cover * w * h:
                continue   # a small figure in the patch, not the thing the detector boxed
            kps = turned_back(k, t, w, h)
            xs = [p[0] for p in kps if p[2] >= 0.5]
            ys = [p[1] for p in kps if p[2] >= 0.5]
            if len(xs) < 5:
                continue   # too few body points to call it a body
            if is_lying([min(xs), min(ys), max(xs), max(ys)], kps):
                return True
    return False


def verified(img, box, verifier, threshold):
    """The learned check (training/build_down_crops.py): P(down) of the cut-out box."""
    H, W = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = max(0, int(box[0] - PAD * bw)), max(0, int(box[1] - PAD * bh))
    x2, y2 = min(W, int(box[2] + PAD * bw)), min(H, int(box[3] + PAD * bh))
    patch = img[y1:y2, x1:x2]
    if patch.shape[0] < 16 or patch.shape[1] < 16:
        return 0.0
    r = verifier.predict(patch, verbose=False)[0]
    yes = [k for k, v in r.names.items() if v in ("lying", "down")][0]   # lying_verify: "lying"; old down_verify: "down"
    return float(r.probs.data[yes])


def gt_boxes(path, w, h):
    out = []
    lab = path.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
    for line in open(lab):
        x, y, bw, bh = map(float, line.split()[1:5])
        out.append([(x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h])
    return out


def sit_vetoed(img, box, pose) -> bool:
    """A pose model sees a clearly upright torso (with knees or ankles) on this box: someone sitting / kneeling."""
    from build_lying_set import clearly_sitting
    H, W = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = max(0, int(box[0] - PAD * bw)), max(0, int(box[1] - PAD * bh))
    x2, y2 = min(W, int(box[2] + PAD * bw)), min(H, int(box[3] + PAD * bh))
    patch = img[y1:y2, x1:x2]
    if patch.shape[0] < 16 or patch.shape[1] < 16:
        return False
    return clearly_sitting(pose.predict(patch, conf=0.25, verbose=False)[0], patch.shape[1], patch.shape[0])


def sweep(a, det, ver):
    """Verifier mode: score every detector box once, then every (detector, verifier) threshold pair."""
    low = min(a.conf)
    veto = YOLO(str(ROOT / a.sit_veto)) if a.sit_veto else None
    # the hand review of every fall_fyp test person: lying (counts), sitting (must NOT raise an alarm), unclear
    review = {(q["image"], q["n"]): q["reviewed"] for q in
              json.loads((ROOT / "outputs/eval/fall_test_posture.json").read_text())}
    falls, sitters = [], []   # per person: [(det conf, P), ...] of the detector boxes on them
    negs = []                 # per negative photo: [(det conf, P), ...]
    for path in sorted(glob.glob(str(ROOT / "data/fall_fyp/test/images/*.jpg"))):
        img = cv2.imread(path)
        d = det.predict(img, conf=low, verbose=False)[0]
        boxes = list(zip(d.boxes.xyxy.tolist(), d.boxes.conf.tolist()))
        scored = [(b, c, verified(img, b, ver, 0)) for b, c in boxes]
        if veto:
            scored = [(b, c, 0.0 if v >= 0.5 and sit_vetoed(img, b, veto) else v) for b, c, v in scored]
        for j, g in enumerate(gt_boxes(path, img.shape[1], img.shape[0])):
            kind = review.get((Path(path).name, j), "lying")
            near = [(c, v) for b, c, v in scored if iou(g, b) >= 0.3]
            if kind == "lying":
                falls.append(near)
            elif kind == "sitting":
                sitters.append(near)
    for folder in NEGATIVES:
        for path in sorted(glob.glob(str(ROOT / folder / "*"))):
            img = cv2.imread(path)
            if img is None:
                continue
            d = det.predict(img, conf=low, verbose=False)[0]
            sc = [(b, c, verified(img, b, ver, 0)) for b, c in zip(d.boxes.xyxy.tolist(), d.boxes.conf.tolist())]
            if veto:
                sc = [(b, c, 0.0 if v >= 0.5 and sit_vetoed(img, b, veto) else v) for b, c, v in sc]
            negs.append([(c, v) for b, c, v in sc])
    print(f"{len(falls)} people lying, {len(sitters)} sitting (hand-reviewed); {len(negs)} photos with nobody down")
    grid = {}
    for c in a.conf:
        for t in (0.5, 0.7, 0.8, 0.9, 0.95):
            caught = sum(any(dc >= c and v >= t for dc, v in f) for f in falls)
            sat = sum(any(dc >= c and v >= t for dc, v in f) for f in sitters)
            false = sum(any(dc >= c and v >= t for dc, v in n) for n in negs)
            grid[f"{c}/{t}"] = {"lying_caught_pct": round(100 * caught / len(falls), 1),
                                "sitting_alarm_pct": round(100 * sat / max(1, len(sitters)), 1), "false_photos": false}
            print(f"  detector >= {c:.2f}, check >= {t:.2f}: lying caught {100 * caught / len(falls):4.1f}%, "
                  f"sitting alarmed {100 * sat / max(1, len(sitters)):4.1f}%, false alarms on {false} photos")
    out = ROOT / f"outputs/eval/{Path(a.verifier).parent.parent.name or 'verify'}{'_veto' if veto else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"detector": a.detector, "verifier": a.verifier, "fallen_people": len(falls),
                               "negative_photos": len(negs), "grid": grid}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default="models/person_down2.pt")
    ap.add_argument("--pose", default="models/yolo11n-pose.pt")
    ap.add_argument("--conf", type=float, nargs="+", default=[0.15, 0.25, 0.35, 0.5])
    ap.add_argument("--verifier", help="classifier from build_down_crops.py instead of the turned pose check")
    ap.add_argument("--verify-at", type=float, default=0.5, help="P(down) a box needs to pass the verifier")
    ap.add_argument("--sit-veto", default="", help="pose model: a clearly upright torso on a confirmed box vetoes it")
    a = ap.parse_args()
    det, pose = YOLO(str(ROOT / a.detector)), YOLO(str(ROOT / a.pose))
    if a.verifier:
        ver = YOLO(str(ROOT / a.verifier) if not a.verifier.startswith("/") else a.verifier)
        return sweep(a, det, ver)
    else:
        confirmed_fn = lambda img, box: confirmed(img, box, pose)  # noqa: E731
    low = min(a.conf)
    res = {c: {"falls_caught": 0, "falls_detector_only": 0, "false_photos": 0, "false_detector_only": 0}
           for c in a.conf}
    total, negs = 0, 0
    for path in sorted(glob.glob(str(ROOT / "data/fall_fyp/test/images/*.jpg"))):
        img = cv2.imread(path)
        gts = gt_boxes(path, img.shape[1], img.shape[0])
        total += len(gts)
        d = det.predict(img, conf=low, verbose=False)[0]
        boxes = [(b, c, None) for b, c in zip(d.boxes.xyxy.tolist(), d.boxes.conf.tolist())]
        for g in gts:
            near = [x for x in boxes if iou(g, x[0]) >= 0.3]
            for c in a.conf:
                cands = [x for x in near if x[1] >= c]
                res[c]["falls_detector_only"] += bool(cands)
                res[c]["falls_caught"] += any(confirmed_fn(img, x[0]) for x in cands)
    for folder in NEGATIVES:
        for path in sorted(glob.glob(str(ROOT / folder / "*"))):
            img = cv2.imread(path)
            if img is None:
                continue
            negs += 1
            d = det.predict(img, conf=low, verbose=False)[0]
            boxes = list(zip(d.boxes.xyxy.tolist(), d.boxes.conf.tolist()))
            ok = {i: confirmed_fn(img, b) for i, (b, c) in enumerate(boxes)}
            for c in a.conf:
                res[c]["false_detector_only"] += any(s >= c for _, s in boxes)
                res[c]["false_photos"] += any(ok[i] for i, (_, s) in enumerate(boxes) if s >= c)
    print(f"{total} fallen people; {negs} photos with nobody down")
    for c in a.conf:
        r = res[c]
        print(f"  detector >= {c:.2f}: caught {100 * r['falls_caught'] / total:4.1f}% "
              f"(detector alone {100 * r['falls_detector_only'] / total:4.1f}%), false alarms on "
              f"{r['false_photos']} photos (detector alone {r['false_detector_only']})")
    out = ROOT / "outputs/eval/down_confirm.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.verifier:
        out = out.with_name(f"down_verify_{a.verify_at:.2f}.json")
    out.write_text(json.dumps({"detector": a.detector, "pose": a.pose, "verifier": a.verifier,
                               "verify_at": a.verify_at, "fallen_people": total,
                               "negative_photos": negs, "by_conf": res}, indent=2))


if __name__ == "__main__":
    main()
