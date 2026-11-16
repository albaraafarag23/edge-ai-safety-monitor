"""Makes the hospital demo's "camera": a video that shows each CPPE-5 test photo for a few seconds, placed in the
plugin's zones (most in the isolation room on the right, every sixth in the medication store on the left).

    python training/make_hospital_demo.py        # after training/build_medical_ppe.py
Writes outputs/hospital_demo/media/demo/hospital.mp4 (docker-compose.hospital-demo.yml plays it).
"""
import glob
import os

import cv2
import numpy as np

W, H, FPS, SECONDS = 1920, 1080, 10, 6   # 6 s a photo: longer than the rules' 3-5 s waiting time
OUT = "outputs/hospital_demo/media/demo/hospital.mp4"

files = sorted(glob.glob("data/medical_ppe/images/test/*.jpg"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
for folder in ("config", "faces"):
    os.makedirs(f"outputs/hospital_demo/{folder}", exist_ok=True)
out = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
for i, path in enumerate(files):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    scale = min(H / h, (W * 0.55) / w)
    img = cv2.resize(img, (int(w * scale), int(h * scale)))
    canvas = np.full((H, W, 3), 235, np.uint8)
    x = 0 if i % 6 == 5 else W - img.shape[1]
    canvas[H - img.shape[0]:, x:x + img.shape[1]] = img
    for _ in range(FPS * SECONDS):
        out.write(canvas)
out.release()
print(f"{len(files)} photos, {len(files) * SECONDS} s -> {OUT}")
