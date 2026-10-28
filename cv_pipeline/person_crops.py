"""Head-and-upper-body crops of detected people, for classifiers that look at one person at a time
(the smoking-act model). Same crop as the training data: keep in step with training/build_smoking_crops.py.
"""
import cv2
import numpy as np


def upper_body_box(person, img_w, img_h, pad=0.1):
    """Head and upper body of a person box (x1, y1, x2, y2), padded and made square. May extend past the image.

    Standing person (tall box): the top half. Half-body or close-up: most or all of the box.
    """
    x1, y1, x2, y2 = person
    w, h = x2 - x1, y2 - y1
    h = min(h, max(0.5 * h, 1.2 * w))
    side = max(w, h) * (1 + 2 * pad)
    cx, cy = (x1 + x2) / 2, y1 + h / 2
    return cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2


def cut(img, box, size):
    """Crop a box that may extend past the image, filling the outside with grey (114, as YOLO letterboxing)."""
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    h, w = img.shape[:2]
    out = np.full((y2 - y1, x2 - x1, 3), 114, np.uint8)
    sx1, sy1, sx2, sy2 = max(x1, 0), max(y1, 0), min(x2, w), min(y2, h)
    if sx2 > sx1 and sy2 > sy1:
        out[sy1 - y1:sy2 - y1, sx1 - x1:sx2 - x1] = img[sy1:sy2, sx1:sx2]
    return cv2.resize(out, (size, size), interpolation=cv2.INTER_AREA)
