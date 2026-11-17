"""Lying or sitting? The fall photos (fall_fyp) mark both as "Fall-Detected", but the site rule is about people
LYING down only: someone sitting on the ground (resting, eating) is not an alarm (user's decision, 2026-11-17).

A pose model is poor at bodies on the ground but good at upright torsos, so the test is one-sided: a clearly
upright torso (shoulders and hips found, torso within UPRIGHT_DEG of vertical, the body filling a fair part of
the cut-out) means sitting / kneeling / crouching; anything else stays "lying".

    from down_posture import posture   ->  "sitting" | "lying"

Checked by eye on all 422 people of the fall_fyp test split (outputs/eval/fall_test_posture.json keeps the
reviewed labels; see training/README.md).
"""
import math

import cv2

UPRIGHT_DEG = 40
MIN_COVER = 0.3
KP = 0.5
PAD = 0.2


def _mid(k, a, b):
    pts = [k[i][:2] for i in (a, b) if k[i][2] >= KP]
    return None if not pts else (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def cut(img, box, pad=PAD):
    H, W = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = max(0, int(box[0] - pad * bw)), max(0, int(box[1] - pad * bh))
    x2, y2 = min(W, int(box[2] + pad * bw)), min(H, int(box[3] + pad * bh))
    return img[y1:y2, x1:x2]


def posture_of_patch(patch, pose) -> str:
    h, w = patch.shape[:2]
    if h < 16 or w < 16:
        return "lying"
    r = pose.predict(patch, conf=0.3, verbose=False)[0]
    for b, k in zip(r.boxes.xyxy.tolist(), r.keypoints.data.tolist()):
        if (b[2] - b[0]) * (b[3] - b[1]) < MIN_COVER * w * h:
            continue
        sh, hp = _mid(k, 5, 6), _mid(k, 11, 12)
        if sh is None or hp is None:
            continue
        dx, dy = hp[0] - sh[0], hp[1] - sh[1]
        if dy > 0 and math.degrees(math.atan2(abs(dx), dy)) < UPRIGHT_DEG:   # hips below shoulders, near vertical
            return "sitting"
    return "lying"


def posture(img, box, pose) -> str:
    return posture_of_patch(cut(img, box), pose)


if __name__ == "__main__":
    # label the fall_fyp test people and draw review sheets
    import glob
    import json
    import sys
    from pathlib import Path

    import numpy as np
    from ultralytics import YOLO

    root = Path(__file__).resolve().parent.parent
    pose = YOLO(sys.argv[1] if len(sys.argv) > 1 else "yolo11m-pose.pt")
    sheets = Path(sys.argv[2] if len(sys.argv) > 2 else "outputs/eval/fall_test_sheets")
    sheets.mkdir(parents=True, exist_ok=True)
    people = []
    for f in sorted(glob.glob(str(root / "data/fall_fyp/test/images/*.jpg"))):
        img = cv2.imread(f)
        H, W = img.shape[:2]
        for j, line in enumerate(open(f.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt")):
            x, y, bw, bh = map(float, line.split()[1:5])
            box = [(x - bw / 2) * W, (y - bh / 2) * H, (x + bw / 2) * W, (y + bh / 2) * H]
            people.append({"image": Path(f).name, "n": j, "box": [round(v, 1) for v in box],
                           "auto": posture(img, box, pose)})
    for label in ("sitting", "lying"):
        group = [(i, p) for i, p in enumerate(people) if p["auto"] == label]
        for s in range(0, len(group), 40):
            tiles = []
            for i, p in group[s:s + 40]:
                img = cv2.imread(str(root / "data/fall_fyp/test/images" / p["image"]))
                c = cut(img, p["box"], 0.35).copy()
                k = 200 / max(c.shape[:2])
                c = cv2.resize(c, (max(1, int(c.shape[1] * k)), max(1, int(c.shape[0] * k))))
                t = np.full((220, 200, 3), 255, np.uint8)
                t[:c.shape[0], :c.shape[1]] = c
                cv2.putText(t, str(i), (3, 216), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                tiles.append(t)
            while len(tiles) % 8:
                tiles.append(np.full((220, 200, 3), 255, np.uint8))
            cv2.imwrite(str(sheets / f"{label}_{s // 40:02d}.jpg"),
                        np.vstack([np.hstack(tiles[r:r + 8]) for r in range(0, len(tiles), 8)]))
    out = root / "outputs/eval/fall_test_posture.json"
    out.write_text(json.dumps(people, indent=1))
    print({lab: sum(p["auto"] == lab for p in people) for lab in ("sitting", "lying")}, "->", out)
