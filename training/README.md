# Training

Run everything from the repo root with the `yoloenv` Python. Scripts only read datasets and videos;
all results go to `outputs/`.

## 1. Check a dataset
    python training/check_dataset.py data/<dataset>/data.yaml
Report: `outputs/dataset_checks/<dataset>.json`. It lists images with no label file,
malformed label lines, instances per class, class imbalance, and identical images
shared between splits.

## 2. Profile the camera (staged footage, no labels needed)
    python training/profile_footage.py recordings/ --out outputs/camera_profile.json
Measures person and head sizes, lighting, and resolution, then suggests an `imgsz` and
augmentation settings.

## 3. Train
    python training/train.py data/<dataset>/data.yaml --name baseline_n
    python training/train.py data/<dataset>/data.yaml --model yolo11s.pt --name baseline_s
    python training/train.py data/<dataset>/data.yaml --profile outputs/camera_profile.json --name matched_s
Saves to `outputs/runs/<name>/`:
- `run_config.json`: exact settings, versions and git commit
- `weights/best.pt`: the trained model
- `eval_test/metrics.json` and `per_class.csv`: test-split metrics

Each run also adds a row to `outputs/runs/summary.csv`.

## 4. Evaluate on another test set (e.g. staged footage)
    python training/eval.py outputs/runs/<name>/weights/best.pt data/staged/data.yaml --name <name>_staged
Results: `outputs/eval/<name>_staged/metrics.json` and `per_class.csv`.

## Staged footage → frames for labeling
    python training/extract_frames.py recordings/ --out data/staged_frames --every 2
Each clip gets its own folder. Keep whole clips for testing, and never split one clip
between train and test.
