"""Train a YOLO detector, then evaluate it and log everything to outputs/runs/<name>/.

Each run saves run_config.json (exact settings, versions, git commit), the Ultralytics
training output, test-split metrics, and adds one row to outputs/runs/summary.csv so
runs can be compared side by side.

    python training/train.py data/construction-ppe/data.yaml --name baseline_n
    python training/train.py data/x/data.yaml --model yolo11s.pt --epochs 150 --name css_s
    python training/train.py data/x/data.yaml --profile outputs/camera_profile.json --name css_s_matched
"""
import argparse
import csv
import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path

import torch
import ultralytics
import yaml
from ultralytics import YOLO

from eval import evaluate, print_result

RUNS_DIR = Path("outputs/runs").resolve()


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).parent).stdout.strip() or None
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="dataset yaml")
    ap.add_argument("--name", required=True, help="run name (folder under outputs/runs/)")
    ap.add_argument("--model", default="yolo11n.pt", help="starting weights (default yolo11n.pt)")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=None, help="default 640, or the camera profile's value")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--patience", type=int, default=30, help="stop early after this many epochs without improvement")
    ap.add_argument("--device", default=None, help="e.g. 0 or cpu (default: GPU if available)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--profile", type=Path, help="camera_profile.json from profile_footage.py")
    ap.add_argument("--workers", type=int, default=2,
                    help="data loading processes; more is faster but uses more RAM (8 ran out on 16 GB)")
    args = ap.parse_args()

    run_dir = RUNS_DIR / args.name
    if run_dir.exists():
        raise SystemExit(f"Run '{args.name}' already exists at {run_dir}. Pick another --name.")

    augment, profile = {}, None
    if args.profile:
        profile = json.loads(args.profile.read_text())
        augment = profile["recommended"].get("augment", {})
        if args.imgsz is None:
            args.imgsz = profile["recommended"]["imgsz"]
    imgsz = args.imgsz or 640

    config = {
        "run": args.name,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "data": str(Path(args.data).resolve()),
        "dataset": yaml.safe_load(Path(args.data).read_text()),
        "model": args.model,
        "epochs": args.epochs, "imgsz": imgsz, "batch": args.batch, "patience": args.patience, "seed": args.seed,
        "augment_overrides": augment,
        "camera_profile": str(args.profile.resolve()) if args.profile else None,
        "git_commit": git_commit(),
        "versions": {"ultralytics": ultralytics.__version__, "torch": torch.__version__,
                     "python": platform.python_version()},
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }
    run_dir.mkdir(parents=True)
    (run_dir / "run_config.json").write_text(json.dumps(config, indent=2))
    print(f"Run '{args.name}': {args.model}, imgsz {imgsz}, {args.epochs} epochs, augment {augment or 'default'}")

    model = YOLO(args.model)
    model.train(data=args.data, epochs=args.epochs, imgsz=imgsz, batch=args.batch, patience=args.patience,
                device=args.device, seed=args.seed, deterministic=True, workers=args.workers,
                project=str(RUNS_DIR), name=args.name, exist_ok=True, **augment)

    best = run_dir / "weights" / "best.pt"
    split = "test" if "test" in config["dataset"] else "val"
    result, eval_dir = evaluate(best, args.data, split=split, imgsz=imgsz,
                                out_dir=run_dir / f"eval_{split}", device=args.device)
    print_result(result, eval_dir)

    summary = RUNS_DIR / "summary.csv"
    row = {"run": args.name, "finished_at": datetime.now().isoformat(timespec="seconds"),
           "model": args.model, "data": Path(args.data).parent.name, "imgsz": imgsz, "epochs": args.epochs,
           "eval_split": split, **{k: v for k, v in result["overall"].items()},
           "inference_ms": result["speed_ms_per_image"].get("inference"), "gpu": config["gpu"]}
    new = not summary.exists()
    with open(summary, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"Added to {summary}")


if __name__ == "__main__":
    main()
