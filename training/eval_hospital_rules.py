"""Gloves / eye protection judged the way the hospital rules judge them, per person, not per box.

    python training/eval_hospital_rules.py models/medical_ppe.pt outputs/runs/medical_ppe3_s/weights/best.pt

RULE_GLOVES_01 raises an alarm when NO Gloves box overlaps a person (overlap_of >= 0.5, as event_engine/rules.py),
RULE_EYES_01 when no Goggles or Face Shield box does. So for every labelled person who IS wearing the item
(a labelled box of it overlaps them) we ask: does the model find at least one on them? A miss there is a
false alarm on a person doing everything right. Labelled people are used so the PPE model is judged, not the
person finder. Missing labels in a test set can only hide wearers, never invent them, so this number is
trustworthy even on the Biosafety photos.

People with no labelled item are counted too ("flagged"), but that is NOT a miss rate: their hands or eyes may
simply be out of view or unlabelled.

Writes outputs/eval/hospital_rules.json.
"""
import json
import os
import sys
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
SETS = {"colour (CPPE-5)": ROOT / "data/medical_ppe3/test_colour",
        "lab, black-and-white": ROOT / "data/medical_ppe3/test_biosafety"}
NAMES = ["Person", "Coverall", "Face Shield", "Gloves", "Goggles", "Mask"]
ITEMS = {"gloves": {"Gloves"}, "eye protection": {"Goggles", "Face Shield"}, "mask": {"Mask"}, "gown": {"Coverall"}}
CONF = float(os.environ.get("RULE_CONF", 0.4))  # plugin default_confidence
MIN_OVERLAP = 0.5   # rules.py min_overlap


def xyxy(b):
    x, y, w, h = b
    return x - w / 2, y - h / 2, x + w / 2, y + h / 2


def overlap_of(inner, outer):
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    iw, ih = max(0, min(ix2, ox2) - max(ix1, ox1)), max(0, min(iy2, oy2) - max(iy1, oy1))
    area = (ix2 - ix1) * (iy2 - iy1)
    return iw * ih / area if area > 0 else 0


def on(person, boxes, classes):
    return any(c in classes and overlap_of(b, person) >= MIN_OVERLAP for c, b in boxes)


def evaluate(model_path):
    model = YOLO(model_path)
    out = {}
    for set_name, d in SETS.items():
        r = {item: {"wearing": 0, "found": 0, "not_labelled": 0, "flagged": 0} for item in ITEMS}
        for img in sorted((d / "images").iterdir()):
            gt = []
            for line in (d / "labels" / (img.stem + ".txt")).read_text().splitlines():
                p = line.split()
                gt.append((NAMES[int(p[0])], xyxy([float(v) for v in p[1:5]])))
            res = model(str(img), verbose=False, conf=CONF)[0]
            pred = [(res.names[int(b.cls[0])], tuple(b.xywhn[0].tolist())) for b in res.boxes]
            pred = [(c, xyxy(b)) for c, b in pred]
            for c, person in gt:
                if c != "Person":
                    continue
                for item, classes in ITEMS.items():
                    seen = on(person, pred, classes)
                    if on(person, gt, classes):
                        r[item]["wearing"] += 1
                        r[item]["found"] += seen
                    else:
                        r[item]["not_labelled"] += 1
                        r[item]["flagged"] += not seen
        out[set_name] = r
    return out


def main():
    models = sys.argv[1:] or [str(ROOT / "models/medical_ppe.pt")]
    results = {m: evaluate(m) for m in models}
    for set_name in SETS:
        print(f"== {set_name}")
        for item in ITEMS:
            row = []
            for m in models:
                r = results[m][set_name][item]
                pct = 100 * r["found"] / max(1, r["wearing"])
                fl = 100 * r["flagged"] / max(1, r["not_labelled"])
                row.append(f"{pct:5.1f}% of {r['wearing']} wearers seen ({r['wearing'] - r['found']} false alarms; {fl:.0f}% of unlabelled flagged)")
            print(f"  {item:15s} " + "  ->  ".join(row))
    out = ROOT / "outputs/eval/hospital_rules.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"written {out}")


if __name__ == "__main__":
    main()
