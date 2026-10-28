"""Run the smoking-act chain on photos: find people, crop head and upper body, classify each crop.

    python training/predict_smoking_act.py outputs/runs/smoking_act_s/weights/best.pt ~/Downloads/smoking_0024.jpg
    python training/predict_smoking_act.py <weights> photo1.jpg photo2.webp --out outputs/smoking_act_checks

Prints each person's answer (smoking / holding / not_smoking, with probabilities) and saves each photo with the
crop squares drawn: red = smoking at --threshold (what raises an alert), amber = holding, green = not smoking.
Uses the same crop rule as the training data (build_smoking_crops.py).
"""
import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO

from build_smoking_crops import cut, upper_body_box


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", help="smoking / not-smoking classifier")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--person-model", default="yolo11s-pose.pt")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--crop", type=int, default=256, help="crop size the model was trained on (384 for the m320 run)")
    ap.add_argument("--imgsz", type=int, default=224, help="model input size (320 for the m320 run)")
    ap.add_argument("--out", type=Path, default=Path("outputs/smoking_act_checks"))
    args = ap.parse_args()

    people_model, cls = YOLO(args.person_model), YOLO(args.weights)
    smoking = {v: k for k, v in cls.names.items()}["smoking"]
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.images:
        img = cv2.imread(str(path))
        if img is None:
            print(f"{path}: can't read")
            continue
        h, w = img.shape[:2]
        boxes = people_model.predict(img, classes=[0], conf=0.35, verbose=False)[0].boxes.xyxy.tolist()
        t = max(2, round(max(h, w) / 400))
        print(f"{path.name}: {len(boxes)} people")
        for i, b in enumerate(boxes):
            region = upper_body_box(b, w, h)
            probs = cls.predict(cut(img, region, args.crop), imgsz=args.imgsz, verbose=False)[0].probs.data.tolist()
            p = probs[smoking]
            top = cls.names[max(range(len(probs)), key=probs.__getitem__)]
            label = "smoking" if p >= args.threshold else top if top != "smoking" else "not_smoking"
            col = {"smoking": (31, 68, 200), "holding": (0, 170, 240)}.get(label, (85, 140, 47))
            x1, y1, x2, y2 = (int(v) for v in region)
            cv2.rectangle(img, (x1, y1), (x2, y2), col, t)
            score = probs[{v: k for k, v in cls.names.items()}[label]]
            cv2.putText(img, f"{label} {score:.2f}", (max(x1, 0) + 6, max(y1, 0) + 14 * t),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4 * t, col, t)
            print(f"  person {i + 1}: {label}  (" + ", ".join(f"{cls.names[k]} {v:.2f}" for k, v in enumerate(probs)) + ")")
        out = args.out / (path.stem + ".jpg")
        cv2.imwrite(str(out), img)
        print(f"  saved {out}")


if __name__ == "__main__":
    main()
