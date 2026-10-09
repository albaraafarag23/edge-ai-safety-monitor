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

## Models used by the detector
Copy a trained model into `models/` under the name the plugin uses (`models/` is mounted into the
`cv_pipeline` container at `/models`):

    cp outputs/runs/<name>/weights/best.pt models/construction_ppe.pt

## Smoking model (`models/smoking.pt`)
A second, small model that only finds cigarettes. It runs next to the main model (`extra_models` in the plugin).
Data: CigDet (Mendeley Data, CC BY 4.0, doi:10.17632/6hyrr8typ7.1), 557 images, one class. Copied into the YOLO
layout in `data/cigdet/yolo/` (train 379 / val 67 / test 111, val split with seed 0):

    python training/train.py data/cigdet/yolo/data.yaml --name smoking_cigdet_n --epochs 150
    cp outputs/runs/smoking_cigdet_n/weights/best.pt models/smoking.pt

Limits: the images are 250×250 close-ups where the cigarette fills ~1.5% of the picture, so expect it to work
within a few metres of the camera only, and test it on staged footage before trusting it.

Vapes: the public vape datasets are on Roboflow Universe (e.g. `stelar/vape-cigarette-detection-2`,
`telai/cigarette-vape-detection-xvtxe`; check each licence). They need a free Roboflow API key:

    ROBOFLOW_API_KEY=... python training/download_roboflow.py <workspace> <project> <version> --name vape

Merge with CigDet (class mapping `cigarette`, `vape`), retrain, then set `"enabled": true` on `RULE_SMOKE_02`.
