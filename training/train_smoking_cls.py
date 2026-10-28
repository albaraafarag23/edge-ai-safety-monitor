"""Train the smoking-act crop classifier (smoking / holding / not_smoking) on data/smoking_act2, then test it
and log everything to outputs/runs/<name>/. An alert means the model says "smoking"; holding and not_smoking
both count as no alert.

    python training/train_smoking_cls.py --name smoking_act_s
    python training/train_smoking_cls.py --model yolo11n-cls.pt --name smoking_act_n

Besides the Ultralytics training output, each run saves run_config.json and test_metrics.json: accuracy,
precision / recall for "smoking", the share found per smoking type (cigarette, vape, ...) and the false alarm
rate per holding type and per not-smoking group (each kind of look-alike, workers, ...), at several thresholds. One row goes to outputs/runs/summary_cls.csv.
Build the dataset first: training/build_smoking_crops.py.
"""
import argparse
import csv
import json
import platform
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import torch
import ultralytics
from ultralytics import YOLO

from train import RUNS_DIR, git_commit

THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def test_metrics(weights, data, imgsz, device):
    """Smoking probability for every test crop, scored overall and per smoking type / not-smoking source."""
    rows = [r for r in csv.DictReader(open(data / "manifest.csv"))
            if r["split"] == "test" and r["label"] in ("smoking", "holding", "not_smoking")]  # not dropped ones
    model = YOLO(weights)
    idx = {v: k for k, v in model.names.items()}["smoking"]
    for i in range(0, len(rows), 64):
        chunk = rows[i:i + 64]
        res = model.predict([str(data / r["crop"]) for r in chunk], imgsz=imgsz, device=device, verbose=False)
        for r, p in zip(chunk, res):
            r["p"] = float(p.probs.data[idx])

    # Crops labelled by a model (sort_unsure.py) are scored as their own groups, not in the headline numbers.
    by_model = [r for r in rows if r.get("sorted_by") and r["type"] not in ("pipe", "cigar", "shisha")]
    all_rows, rows = rows, [r for r in rows if r not in by_model]
    out = {"test_crops": len(rows), "test_crops_sorted_by_model": len(by_model), "at_threshold": {}}
    for t in THRESHOLDS:
        tp = sum(r["label"] == "smoking" and r["p"] >= t for r in rows)
        fp = sum(r["label"] == "not_smoking" and r["p"] >= t for r in rows)
        fn = sum(r["label"] == "smoking" and r["p"] < t for r in rows)
        tn = len(rows) - tp - fp - fn
        groups = defaultdict(list)
        for r in all_rows:
            groups[f"{r['label']}/{r['type']}" + (" (sorted by model)" if r in by_model else "")].append(r)
        out["at_threshold"][str(t)] = {
            "accuracy": round((tp + tn) / len(rows), 4),
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "false_alarm_rate": round(fp / (fp + tn), 4) if fp + tn else None,
            # smoking groups: share found; not-smoking groups: share wrongly called smoking
            "by_group": {g: {"n": len(rs), ("found" if g.startswith("smoking") else "false_alarms"):
                             round(sum((r["p"] >= t) for r in rs) / len(rs), 4)} for g, rs in sorted(groups.items())},
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/smoking_act2"))
    ap.add_argument("--name", required=True, help="run name (folder under outputs/runs/)")
    ap.add_argument("--model", default="yolo11s-cls.pt", help="starting weights (ImageNet-pretrained classifier)")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--lr0", type=float, default=0.0005,
                    help="AdamW learning rate; the automatic choice (~0.0016) threw the pretrained model off course")
    ap.add_argument("--device", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2, help="8 ran out of RAM on this 16 GB laptop")
    args = ap.parse_args()

    run_dir = RUNS_DIR / args.name
    if run_dir.exists():
        raise SystemExit(f"Run '{args.name}' already exists at {run_dir}. Pick another --name.")
    data = args.data.resolve()
    counts = {f"{s}/{c.name}": len(list(c.glob("*.jpg"))) for s in ("train", "val", "test")
              for c in sorted((data / s).iterdir()) if c.is_dir()}
    config = {
        "run": args.name, "task": "classify", "started_at": datetime.now().isoformat(timespec="seconds"),
        "data": str(data), "counts": counts, "model": args.model, "epochs": args.epochs, "imgsz": args.imgsz,
        "batch": args.batch, "patience": args.patience, "lr0": args.lr0, "seed": args.seed, "git_commit": git_commit(),
        "versions": {"ultralytics": ultralytics.__version__, "torch": torch.__version__,
                     "python": platform.python_version()},
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }
    run_dir.mkdir(parents=True)
    (run_dir / "run_config.json").write_text(json.dumps(config, indent=2))
    print(f"Run '{args.name}': {args.model}, imgsz {args.imgsz}, {args.epochs} epochs, {counts}")

    YOLO(args.model).train(data=str(data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                           patience=args.patience, optimizer="AdamW", lr0=args.lr0, cos_lr=True, device=args.device, seed=args.seed, deterministic=True,
                           workers=args.workers, project=str(RUNS_DIR), name=args.name, exist_ok=True)

    metrics = test_metrics(run_dir / "weights" / "best.pt", data, args.imgsz, args.device)
    (run_dir / "test_metrics.json").write_text(json.dumps(metrics, indent=2))
    m = metrics["at_threshold"]["0.5"]
    print(json.dumps(m, indent=2))

    summary = RUNS_DIR / "summary_cls.csv"
    row = {"run": args.name, "finished_at": datetime.now().isoformat(timespec="seconds"), "model": args.model,
           "data": data.name, "imgsz": args.imgsz, "test_crops": metrics["test_crops"],
           **{k: m[k] for k in ("accuracy", "precision", "recall", "false_alarm_rate")}, "gpu": config["gpu"]}
    new = not summary.exists()
    with open(summary, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"Test metrics: {run_dir / 'test_metrics.json'}. Added to {summary}")


if __name__ == "__main__":
    main()
