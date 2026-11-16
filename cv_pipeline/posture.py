"""Body posture from a pose model (COCO keypoints): is a person lying down, and for how long have they been still?

Used by an extra model with "pose": true in the plugin (e.g. yolo11n-pose.pt). It reports one box of class
"lying" per person lying down, with attributes {"still_s": seconds without moving}. The rules then decide:
"Person down" = lying for a few seconds; "Sleeping on site" = lying and still for minutes (event_engine, "pose").

Lying means the torso (shoulders to hips) is closer to flat than upright, and the legs aren't standing under
the hips (that would be someone bending over to pick something up). Without usable keypoints, a box much
wider than tall stands in.
"""
import math
import time

# COCO keypoint order
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 5, 6, 11, 12, 13, 14, 15, 16
MIN_KP_CONF = 0.5
TORSO_FLAT_DEG = 50      # torso at least this far from upright
WIDE_BOX = 1.4           # fallback without keypoints: width at least this many times the height
STILL_MOVE = 0.15        # moving more than this share of the box's larger side resets "still"


def _mid(kps, a, b):
    """Midpoint of two keypoints, or the one that is visible, or None."""
    pts = [kps[i][:2] for i in (a, b) if kps[i][2] >= MIN_KP_CONF]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def is_lying(box, kps) -> bool:
    """box: [x1, y1, x2, y2]; kps: 17 x [x, y, confidence] (image pixels)."""
    shoulders, hips = _mid(kps, L_SHOULDER, R_SHOULDER), _mid(kps, L_HIP, R_HIP)
    if shoulders is None or hips is None:
        # part of the body is out of view (a close-up, someone cut off at the edge): can't tell, so not lying,
        # unless the model saw no body points at all, when only the box's shape is left to go on
        if any(k[2] >= MIN_KP_CONF for k in kps):
            return False
        w, h = box[2] - box[0], box[3] - box[1]
        return h > 0 and w / h >= WIDE_BOX
    dx, dy = hips[0] - shoulders[0], hips[1] - shoulders[1]
    torso = math.hypot(dx, dy)
    if torso < 1:
        return False
    angle = math.degrees(math.atan2(abs(dx), abs(dy)))   # 0 = upright, 90 = flat
    if angle < TORSO_FLAT_DEG:
        return False
    # bending over: feet (or at least knees) well below the hips, as when standing
    ankles, knees = _mid(kps, L_ANKLE, R_ANKLE), _mid(kps, L_KNEE, R_KNEE)
    if ankles is not None and ankles[1] - hips[1] > 0.8 * torso:
        return False
    if knees is not None and knees[1] - hips[1] > 0.4 * torso:
        return False
    return True


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Stillness:
    """Per camera: for each lying person, since when they haven't moved."""
    FORGET_S = 3.0   # a lying person unseen this long is forgotten

    def __init__(self):
        self.tracks: list[dict] = []   # {"box", "anchor": centre when they became still, "since", "seen"}

    def update(self, boxes: list[list[float]], now: float | None = None) -> list[float]:
        now = time.time() if now is None else now
        self.tracks = [t for t in self.tracks if now - t["seen"] <= self.FORGET_S]
        out, used = [], set()
        for box in boxes:
            best = max(((i, _iou(box, t["box"])) for i, t in enumerate(self.tracks) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            size = max(box[2] - box[0], box[3] - box[1])
            if best[0] is not None and best[1] >= 0.3:
                t = self.tracks[best[0]]
                used.add(best[0])
                if math.hypot(cx - t["anchor"][0], cy - t["anchor"][1]) > STILL_MOVE * size:
                    t["anchor"], t["since"] = (cx, cy), now
                t["box"], t["seen"] = box, now
            else:
                t = {"box": box, "anchor": (cx, cy), "since": now, "seen": now}
                self.tracks.append(t)
                used.add(len(self.tracks) - 1)
            out.append(now - t["since"])
        return out
