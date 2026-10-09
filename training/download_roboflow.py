"""Download a Roboflow Universe dataset in YOLO format into data/<name>/ (needs a free API key).

    pip install roboflow
    ROBOFLOW_API_KEY=... python training/download_roboflow.py <workspace> <project> <version> --name vape
    e.g. the vape datasets listed in training/README.md

Then check it (training/check_dataset.py) before training. Datasets keep their own licence; note it in
the run name or README when you use one.
"""
import argparse
import os
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("project")
    ap.add_argument("version", type=int)
    ap.add_argument("--name", required=True, help="folder under data/")
    args = ap.parse_args()

    key = os.getenv("ROBOFLOW_API_KEY")
    if not key:
        raise SystemExit("Set ROBOFLOW_API_KEY (free account: roboflow.com, Settings > API Keys)")
    out = Path("data") / args.name
    if out.exists():
        raise SystemExit(f"{out} already exists; pick another --name")

    from roboflow import Roboflow
    project = Roboflow(api_key=key).workspace(args.workspace).project(args.project)
    project.version(args.version).download("yolov11", location=str(out))
    print(f"Saved to {out}. Next: python training/check_dataset.py {out}/data.yaml")


if __name__ == "__main__":
    main()
