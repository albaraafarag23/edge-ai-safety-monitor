"""Old smoking model (3 labels) vs new one (4 labels: + vaping), on the same test crops, the same question:

  - smoking alerts: smokers (cigarette, vape, pipe, ...) found, and false alarms on people not smoking / holding;
    the old model alerts on "smoking", the new one on "smoking" or "vaping" (each with its own 0.5 threshold, as
    the detector does: cv_pipeline classify_people keeps every class over its threshold);
  - vaping: share of vapers called "vaping", and of cigarette smokers wrongly called "vaping".

    python training/eval_vaping.py OLD.pt NEW.pt     -> outputs/eval/vaping.json
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from ultralytics import YOLO

DATA = Path("data/smoking_act2_384")   # the 3-label test set; the 4-label one is the same crops (hard links)
T = 0.5


def probs(weights, rows, imgsz):
    model = YOLO(weights)
    out = []
    for i in range(0, len(rows), 64):
        chunk = rows[i:i + 64]
        for r in model.predict([str(DATA / r["crop"]) for r in chunk], imgsz=imgsz, verbose=False):
            out.append({model.names[k]: float(v) for k, v in enumerate(r.probs.data.tolist())})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--imgsz", type=int, default=320)
    args = ap.parse_args()
    rows = [r for r in csv.DictReader(open(DATA / "manifest.csv"))
            if r["split"] == "test" and r["label"] in ("smoking", "holding", "not_smoking") and not r.get("sorted_by")]
    result = {"test_crops": len(rows)}
    for name, weights in (("old", args.old), ("new", args.new)):
        ps = probs(weights, rows, args.imgsz)
        alert = [p.get("smoking", 0) >= T or p.get("vaping", 0) >= T for p in ps]
        groups = defaultdict(list)
        for r, a, p in zip(rows, alert, ps):
            groups[f"{r['label']}/{r['type']}"].append((a, p))
        smokers = [(a, r) for r, a in zip(rows, alert) if r["label"] == "smoking"]
        not_smoking = [a for r, a in zip(rows, alert) if r["label"] == "not_smoking"]
        holding = [a for r, a in zip(rows, alert) if r["label"] == "holding"]
        tp, fp = sum(a for a, _ in smokers), sum(not_smoking)
        vapers = [p for r, p in zip(rows, ps) if r["label"] == "smoking" and r["type"] == "vape"]
        cigs = [p for r, p in zip(rows, ps) if r["label"] == "smoking" and r["type"] == "cigarette"]
        result[name] = {
            "smokers_found": round(tp / len(smokers), 4),
            "precision_vs_not_smoking": round(tp / (tp + fp), 4) if tp + fp else None,
            "false_alarms_not_smoking": round(fp / len(not_smoking), 4),
            "holding_called_smoking": round(sum(holding) / len(holding), 4),
            "workers_false_alarms": round(sum(a for a, _ in groups["not_smoking/worker"]) / max(len(groups["not_smoking/worker"]), 1), 4),
            "vapers_called_vaping": round(sum(p.get("vaping", 0) >= T for p in vapers) / len(vapers), 4) if vapers else None,
            "cigarettes_called_vaping": round(sum(p.get("vaping", 0) >= T for p in cigs) / len(cigs), 4) if cigs else None,
            "found_by_type": {g.split("/")[1]: round(sum(a for a, _ in v) / len(v), 3)
                              for g, v in sorted(groups.items()) if g.startswith("smoking/")},
        }
    out = Path("outputs/eval/vaping.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
