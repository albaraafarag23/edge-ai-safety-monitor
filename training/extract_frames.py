"""Pull still frames out of recorded clips for labeling. Never changes the videos.

Keeps one frame every --every seconds, skips blurry frames and frames that look almost
the same as the last kept one. Each clip gets its own folder, so whole clips can be
held out for testing (never split one clip between train and test).

    python training/extract_frames.py recordings/ --out data/staged_frames
    python training/extract_frames.py clip1.mp4 clip2.mp4 --out data/staged_frames --every 1
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def sharpness(gray):
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def thumb(gray):
    return cv2.resize(gray, (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)


def extract(video: Path, out_dir: Path, every_s: float, min_sharpness: float, min_change: float):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return {"clip": video.name, "error": "could not open"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * every_s))
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = {"clip": video.name, "fps": fps, "frames_read": 0, "sampled": 0,
             "kept": 0, "skipped_blurry": 0, "skipped_duplicate": 0}
    last = None
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            _, frame = cap.retrieve()
            stats["sampled"] += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            t = thumb(gray)
            if sharpness(gray) < min_sharpness:
                stats["skipped_blurry"] += 1
            elif last is not None and np.abs(t - last).mean() < min_change:
                stats["skipped_duplicate"] += 1
            else:
                cv2.imwrite(str(out_dir / f"{video.stem}_{idx:06d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                stats["kept"] += 1
                last = t
        idx += 1
    stats["frames_read"] = idx
    cap.release()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path, help="video files or folders of videos")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--every", type=float, default=2.0, help="seconds between sampled frames (default 2)")
    ap.add_argument("--min-sharpness", type=float, default=50.0,
                    help="Laplacian variance below this counts as blurry (default 50)")
    ap.add_argument("--min-change", type=float, default=4.0,
                    help="mean pixel difference (0-255) from the last kept frame needed to keep a frame (default 4)")
    args = ap.parse_args()

    videos = []
    for p in args.inputs:
        videos += sorted(v for v in p.rglob("*") if v.suffix.lower() in VIDEO_EXT) if p.is_dir() else [p]
    if not videos:
        raise SystemExit("No videos found")

    log = []
    for v in videos:
        s = extract(v, args.out / v.stem, args.every, args.min_sharpness, args.min_change)
        log.append(s)
        if "error" in s:
            print(f"  {v.name}: ERROR {s['error']}")
        else:
            print(f"  {v.name}: kept {s['kept']} of {s['sampled']} sampled "
                  f"(blurry {s['skipped_blurry']}, duplicate {s['skipped_duplicate']})")

    settings = {k: getattr(args, k) for k in ("every", "min_sharpness", "min_change")}
    (args.out / "extract_log.json").write_text(json.dumps({"settings": settings, "clips": log}, indent=2))
    print(f"\n{sum(s.get('kept', 0) for s in log)} frames from {len(videos)} clips -> {args.out}")


if __name__ == "__main__":
    main()
