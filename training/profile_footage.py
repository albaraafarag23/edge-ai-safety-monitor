"""Measure what the deployment camera sees, using staged footage. No labels needed.

Runs a stock YOLO model to find people, then records person and estimated head sizes in
pixels, where people stand in the frame, brightness and sharpness. From that it suggests
a training image size and augmentation settings; train.py --profile applies them.

    python training/profile_footage.py recordings/ --out outputs/camera_profile.json
    python training/profile_footage.py data/staged_frames/ --model yolo11n.pt
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
HEAD_FRACTION = 0.13      # head is roughly 1/7.5 of a standing person's height
MIN_HEAD_PX = 12          # below this, helmet detection gets unreliable
IMGSZ_CHOICES = [640, 800, 960, 1280]


def frames(inputs, every_s, max_frames):
    """Yields BGR frames from videos (one every every_s seconds) and image files."""
    files = []
    for p in inputs:
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in VIDEO_EXT | IMG_EXT) if p.is_dir() else [p]
    n = 0
    for f in files:
        if f.suffix.lower() in IMG_EXT:
            img = cv2.imread(str(f))
            if img is not None:
                yield img
                n += 1
        else:
            cap = cv2.VideoCapture(str(f))
            step = max(1, round((cap.get(cv2.CAP_PROP_FPS) or 30) * every_s))
            i = 0
            while cap.grab():
                if i % step == 0:
                    _, img = cap.retrieve()
                    yield img
                    n += 1
                    if n >= max_frames:
                        break
                i += 1
            cap.release()
        if n >= max_frames:
            return


def pct(values, ps=(10, 50, 90)):
    if not len(values):
        return None
    return {f"p{p}": round(float(np.percentile(values, p)), 3) for p in ps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path, help="videos, images, or folders of them")
    ap.add_argument("--model", default="yolo11n.pt", help="any model with a person class (default yolo11n.pt)")
    ap.add_argument("--every", type=float, default=1.0, help="seconds between sampled video frames")
    ap.add_argument("--max-frames", type=int, default=2000)
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--out", type=Path, default=Path("outputs/camera_profile.json"))
    args = ap.parse_args()

    model = YOLO(args.model)
    person_ids = [i for i, n in model.names.items() if n.lower() == "person"]
    if not person_ids:
        raise SystemExit(f"{args.model} has no 'person' class")

    sizes, heights, rel_heights, aspects, feet = set(), [], [], [], []
    brightness, contrast, sharp = [], [], []
    n_frames = frames_with_people = 0
    for img in frames(args.inputs, args.every, args.max_frames):
        n_frames += 1
        h, w = img.shape[:2]
        sizes.add((w, h))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        brightness.append(gray.mean())
        contrast.append(gray.std())
        sharp.append(cv2.Laplacian(gray, cv2.CV_64F).var())

        boxes = model.predict(img, conf=args.conf, classes=person_ids, verbose=False)[0].boxes.xyxy.tolist()
        frames_with_people += bool(boxes)
        for x1, y1, x2, y2 in boxes:
            heights.append(y2 - y1)
            rel_heights.append((y2 - y1) / h)
            aspects.append((x2 - x1) / max(y2 - y1, 1))
            feet.append(((x1 + x2) / 2 / w, y2 / h))
    if not n_frames:
        raise SystemExit("No frames found")

    long_side = max(max(s) for s in sizes)
    heads = np.array(heights) * HEAD_FRACTION
    measured = {
        "frames": n_frames,
        "frames_with_people": frames_with_people,
        "people_found": len(heights),
        "resolutions": sorted(f"{w}x{h}" for w, h in sizes),
        "person_height_px": pct(heights),
        "person_height_fraction_of_frame": pct(rel_heights),
        "estimated_head_px": pct(heads),
        "person_box_width_to_height": pct(aspects),
        "feet_y_fraction": pct([f[1] for f in feet]),
        "brightness_0_255": pct(brightness),
        "contrast_std": pct(contrast),
        "sharpness_laplacian_var": pct(sharp),
    }

    notes = []
    if not heights:
        notes.append("No people found: record clips with people in them to get size-based suggestions.")
        imgsz, scale = 640, 0.5
    else:
        # smallest image size where far workers (10th percentile) still have a usable head size,
        # never larger than the camera's own resolution (upscaling adds no detail)
        far_head = float(np.percentile(heads, 10))
        cap = min(IMGSZ_CHOICES, key=lambda s: abs(s - long_side)) if long_side < 1280 else 1280
        imgsz = next((s for s in IMGSZ_CHOICES if s <= cap and far_head * s / long_side >= MIN_HEAD_PX), cap)
        head_at = far_head * imgsz / long_side
        notes.append(f"Far workers' heads are ~{head_at:.0f} px at imgsz {imgsz}.")
        if head_at < MIN_HEAD_PX:
            notes.append("Still below the reliable size even at the largest usable imgsz: move the camera "
                         "closer, zoom in, or accept weaker helmet detection for far workers.")
        if imgsz > 640:
            notes.append(f"imgsz {imgsz} is slower than 640: check FPS on the Jetson before committing.")
        # people look small in this camera -> let training shrink images more than the default
        scale = 0.7 if np.median(rel_heights) < 0.2 else 0.5

    spread = np.percentile(brightness, 90) - np.percentile(brightness, 10)
    hsv_v = 0.6 if spread > 60 else 0.4
    if spread > 60:
        notes.append("Lighting varies a lot between frames: using stronger brightness augmentation.")

    profile = {
        "source": [str(p) for p in args.inputs],
        "model": args.model,
        "measured": measured,
        "recommended": {"imgsz": imgsz, "augment": {"scale": scale, "hsv_v": hsv_v}},
        "notes": notes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(profile, indent=2))

    print(f"Frames: {n_frames} ({frames_with_people} with people, {len(heights)} people)")
    print(f"Resolution: {', '.join(measured['resolutions'])}")
    for k in ("person_height_px", "estimated_head_px", "brightness_0_255"):
        print(f"{k:20} {measured[k]}")
    print(f"Recommended: imgsz={imgsz}  augment={profile['recommended']['augment']}")
    for n in notes:
        print(" -", n)
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
