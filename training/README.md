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

## Smoking-act model: smoking / holding / not-smoking person crops

Instead of finding the cigarette, crop each person's head and upper body and classify the crop as smoking or
not smoking (cigarette, vape, pipe, cigar, shisha). Plan and reasons: `docs/team_notes.md` section 3.

Download the sets (Roboflow API key in `.env`; all CC BY 4.0 except mi-privado, MIT):

    export ROBOFLOW_API_KEY=...
    python training/download_roboflow.py hugefissure cigarette-vape-detection-lagrc 1 --name smk_cig_vape_5k
    python training/download_roboflow.py stelar vape-cigarette-detection-2 2 --name smk_stelar_vape_cig
    python training/download_roboflow.py smoketrack smoketrack-eldf7 3 --name smk_smoketrack
    python training/download_roboflow.py object-detection-vnf3r smoking-qbqdv 1 --name smk_vnf3r
    # mi-privado has no published version: fork it on Roboflow, generate a version, then download the fork
    python training/download_roboflow.py we-love-football-s-workspace cigarette-detection-iggcm-mlrhi 1 --name smk_miprivado_17k
    # cigar / pipe / shisha (classification): v3 has the smoking photos, v4 the "normal" ones
    python -c "from roboflow import Roboflow; import os; p=Roboflow(api_key=os.environ['ROBOFLOW_API_KEY']).workspace('object-detection-trurj').project('cigar-pipe-shisha-classification'); p.version(3).download('folder', location='data/smk_cigar_pipe_shisha_cls_v3'); p.version(4).download('folder', location='data/smk_cigar_pipe_shisha_cls')"
    # Mendeley (RAR, needs unrar): j45dj8bgfc -> data/smk_mendeley_smoker_1120, 7b52hhzs3r -> data/smk_mendeley_smoking_2400

Build the crops (person finder: COCO pose model, so a smoking crop needs a visible face):

    python training/build_smoking_crops.py          # -> data/smoking_act/{train,val,test}/{smoking,not_smoking}

`data/smoking_act/manifest.csv` lists each crop's source, licence, smoking type and original photo; counts, skips
and one sample sheet per type go to `outputs/dataset_checks/smoking_act/`. The crop region is
`upper_body_box()` in that script; the live detector must cut the same region from its Person boxes.

Current set and model (2026-10-21): `data/smoking_act2` (three labels; see `docs/team_notes.md` section 3).

    python training/build_smoking_crops.py                                  # -> data/smoking_act2 (+ unsure/)
    python training/train_smoking_cls.py --name smoking_act2_s              # first model, clean labels only
    python training/sort_unsure.py outputs/runs/smoking_act2_s/weights/best.pt --apply
    python training/apply_review.py outputs/dataset_checks/smoking_act2/review_*.json data/smoking_act2
    python training/recut_crops.py data/smoking_act2 data/smoking_act2_384 --size 384
    python training/train_smoking_cls.py --data data/smoking_act2_384 --model yolo11m-cls.pt --imgsz 320 \
        --batch 32 --name smoking_act2_m320_clean                          # model in use
    python training/predict_smoking_act.py outputs/runs/smoking_act2_m320_clean/weights/best.pt photo.jpg \
        --crop 384 --imgsz 320

The hand-checked labels are in `outputs/dataset_checks/smoking_act2/review_*.json` (re-applied by apply_review.py).
