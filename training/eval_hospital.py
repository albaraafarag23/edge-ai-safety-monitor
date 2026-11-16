"""Old hospital model vs new one, per item (gloves, goggles, ...), on both test sets of data/medical_ppe2:
CPPE-5's own test pictures and the Biosafety test pictures. Precision, recall and mAP50 per class.

    python training/eval_hospital.py models/medical_ppe.pt outputs/runs/medical_ppe2_s/weights/best.pt
-> outputs/eval/hospital.json
"""
import argparse
import json
from pathlib import Path

from ultralytics import YOLO

SETS = {"cppe5_test": ("data/medical_ppe2/data_local.yaml", "test"),
        "biosafety_test": ("data/medical_ppe2/data_test_biosafety.yaml", "val")}


def per_class(weights: str, data: str, split: str) -> dict:
    m = YOLO(weights).val(data=data, split=split, imgsz=640, batch=16, plots=False, verbose=False, workers=2)
    names = m.names
    out = {}
    for i, c in enumerate(m.box.ap_class_index):
        out[names[int(c)]] = {"precision": round(float(m.box.p[i]), 3), "recall": round(float(m.box.r[i]), 3),
                              "mAP50": round(float(m.box.ap50[i]), 3)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    args = ap.parse_args()
    result = {name: {"old": per_class(args.old, *spec), "new": per_class(args.new, *spec)} for name, spec in SETS.items()}
    out = Path("outputs/eval/hospital.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    for name, r in result.items():
        print(f"== {name}")
        for cls in sorted(set(r["old"]) | set(r["new"])):
            o, n = r["old"].get(cls, {}), r["new"].get(cls, {})
            print(f"  {cls:12} recall {o.get('recall', '-')} -> {n.get('recall', '-')}   "
                  f"precision {o.get('precision', '-')} -> {n.get('precision', '-')}   mAP50 {o.get('mAP50', '-')} -> {n.get('mAP50', '-')}")


if __name__ == "__main__":
    main()
