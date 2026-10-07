"""Evaluate trained weights on a dataset split and save the metrics for reuse.

Writes outputs/eval/<name>/metrics.json (overall + per class + speed) and per_class.csv.

    python training/eval.py outputs/runs/baseline_n/weights/best.pt data/construction-ppe/data.yaml
    python training/eval.py best.pt data/staged/data.yaml --split test --name staged_test
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from ultralytics import YOLO


def evaluate(weights, data, split="test", imgsz=640, out_dir=None, device=None, batch=16):
    weights = Path(weights)
    out_dir = Path(out_dir or Path("outputs/eval") / f"{weights.parent.parent.name}_{split}").resolve()
    model = YOLO(str(weights))
    m = model.val(data=str(data), split=split, imgsz=imgsz, batch=batch, device=device,
                  project=str(out_dir.parent), name=out_dir.name, exist_ok=True, plots=True, verbose=False)

    names = m.names
    counts = getattr(m, "nt_per_class", None)
    per_class = []
    for i, c in enumerate(m.box.ap_class_index):
        c = int(c)
        per_class.append({
            "class": names[c],
            "instances": int(counts[c]) if counts is not None else None,
            "precision": round(float(m.box.p[i]), 4),
            "recall": round(float(m.box.r[i]), 4),
            "mAP50": round(float(m.box.ap50[i]), 4),
            "mAP50-95": round(float(m.box.ap[i]), 4),
        })
    result = {
        "weights": str(weights.resolve()),
        "data": str(Path(data).resolve()),
        "split": split,
        "imgsz": imgsz,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "overall": {
            "precision": round(float(m.box.mp), 4),
            "recall": round(float(m.box.mr), 4),
            "mAP50": round(float(m.box.map50), 4),
            "mAP50-95": round(float(m.box.map), 4),
        },
        "speed_ms_per_image": {k: round(v, 2) for k, v in m.speed.items()},
        "per_class": per_class,
        "classes_not_in_split": [n for c, n in names.items() if c not in set(int(x) for x in m.box.ap_class_index)],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(result, indent=2))
    with open(out_dir / "per_class.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_class[0]) if per_class else ["class"])
        w.writeheader()
        w.writerows(per_class)
    return result, out_dir


def print_result(result, out_dir):
    o = result["overall"]
    print(f"\n{result['split']} split — P {o['precision']:.3f}  R {o['recall']:.3f}  "
          f"mAP50 {o['mAP50']:.3f}  mAP50-95 {o['mAP50-95']:.3f}  "
          f"inference {result['speed_ms_per_image'].get('inference', 0):.1f} ms/img (this machine)")
    width = max((len(r["class"]) for r in result["per_class"]), default=5)
    print(f"  {'class':{width}}  {'n':>6}  {'P':>6}  {'R':>6}  {'mAP50':>6}  {'50-95':>6}")
    for r in sorted(result["per_class"], key=lambda r: r["mAP50"]):
        print(f"  {r['class']:{width}}  {r['instances'] or '':>6}  {r['precision']:6.3f}  {r['recall']:6.3f}  "
              f"{r['mAP50']:6.3f}  {r['mAP50-95']:6.3f}")
    if result["classes_not_in_split"]:
        print(f"  (no examples in this split: {result['classes_not_in_split']})")
    print(f"Saved: {out_dir}/metrics.json, per_class.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights")
    ap.add_argument("data")
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default=None)
    ap.add_argument("--name", help="output folder name under outputs/eval/")
    args = ap.parse_args()

    out_dir = Path("outputs/eval") / args.name if args.name else None
    result, out_dir = evaluate(args.weights, args.data, args.split, args.imgsz, out_dir, args.device, args.batch)
    print_result(result, out_dir)


if __name__ == "__main__":
    main()
