"""Person down, judged over time: a fall detector proposes, a "lying or not" check confirms, and a person only
counts as down when most recent checks agree. Sitting on the ground does not count (user's decision).

Per camera, FallWatch follows each candidate box across checks (by overlap) and keeps:
  votes    the last VOTE_WINDOW_S of checks: confirmed lying, or not (the check said no, or the detector didn't
           find it this time). Reported as down once at least MIN_CHECKS checks fall in the window and at least
           VOTE_SHARE of them said lying. One bad frame (a shadow, a bag) never lasts; a real fall gets many tries.
  fell     True when an upright person (the main model's person box, clearly taller than wide) was where this
           person now lies within LOOKBACK_S before they were first seen down: the fall itself was seen. A truck
           or a railing was never standing, so it can't have fallen. The rule engine lets a seen fall raise the
           alarm quickly and makes a person found already down (no fall seen) wait longer (unseen_fall_after_s).
  down_s   how long this person has been reported down without a break (FORGET_S).
Times come from the caller (the frame's time), so the logic is the same live and in tests.
"""
from collections import deque

VOTE_WINDOW_S = 3.0
MIN_CHECKS = 3
VOTE_SHARE = 0.6
FORGET_S = 3.0        # a candidate unseen this long is forgotten
LOOKBACK_S = 4.0      # an upright person this recently, at this spot: the fall was seen
MATCH_IOU = 0.3
UPRIGHT_RATIO = 1.3   # a person box at least this many times taller than wide counts as upright


PAD = 0.2             # margin around a box when it is cut out for the lying check (as in its training crops,
                      # training/build_down_crops.py)
MAX_CANDIDATES = 5    # boxes checked per frame at most (the most confident first)


def pad_cut(image, box, pad: float = PAD):
    """The box with a margin, cut out of the image (None when too small to judge)."""
    H, W = image.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    x1, y1 = max(0, int(box[0] - pad * bw)), max(0, int(box[1] - pad * bh))
    x2, y2 = min(W, int(box[2] + pad * bw)), min(H, int(box[3] + pad * bh))
    patch = image[y1:y2, x1:x2]
    return patch if patch.shape[0] >= 16 and patch.shape[1] >= 16 else None


def iou(a, b) -> float:
    ix, iy = max(0.0, min(a[2], b[2]) - max(a[0], b[0])), max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def where_they_stood(upright, down) -> bool:
    """Could someone standing in box `upright` have ended up lying in box `down`? Their feet stay roughly where
    they were and the body lands around them: the feet must be inside the down box grown by its own size."""
    fx, fy = (upright[0] + upright[2]) / 2, upright[3]
    w, h = down[2] - down[0], down[3] - down[1]
    size = max(w, h, upright[3] - upright[1])
    return down[0] - size / 2 <= fx <= down[2] + size / 2 and down[1] - size / 2 <= fy <= down[3] + size / 2


class FallWatch:
    def __init__(self):
        self.tracks: list[dict] = []
        self.upright: deque = deque()   # (time, box) of upright people, the last LOOKBACK_S

    def note_people(self, now: float, person_boxes: list[list[float]]):
        """Every frame: where the upright people are (the main model's person boxes)."""
        for b in person_boxes:
            w, h = b[2] - b[0], b[3] - b[1]
            if w > 0 and h >= UPRIGHT_RATIO * w:
                self.upright.append((now, list(b)))
        while self.upright and now - self.upright[0][0] > LOOKBACK_S + FORGET_S:
            self.upright.popleft()

    def _seen_falling(self, box, first_seen: float) -> bool:
        return any(first_seen - LOOKBACK_S <= t <= first_seen and where_they_stood(b, box)
                   for t, b in self.upright)

    def update(self, now: float, candidates: list[tuple[list[float], bool]]) -> list[dict]:
        """One check: the fall detector's boxes this frame, each with whether the lying check confirmed it.
        Returns the people down now: {"bbox", "share", "checks", "fell", "down_s"}."""
        self.tracks = [t for t in self.tracks if now - t["seen"] <= FORGET_S]
        used = set()
        for box, lying in sorted(candidates, key=lambda c: -c[1]):   # confirmed boxes pick their track first
            best = max(((i, iou(box, t["box"])) for i, t in enumerate(self.tracks) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            if best[0] is not None and best[1] >= MATCH_IOU:
                t = self.tracks[best[0]]
            else:
                t = {"votes": deque(), "first": now, "fell": None, "down_since": None}
                self.tracks.append(t)
                best = (len(self.tracks) - 1, 0.0)
            used.add(best[0])
            t["box"], t["seen"] = list(box), now
            t["votes"].append((now, bool(lying)))
            if lying and t["fell"] is None:
                t["fell"] = self._seen_falling(box, now)   # decided at the first confirmed check
        for i, t in enumerate(self.tracks):
            if i not in used:
                t["votes"].append((now, False))   # checked this frame and not found
        out = []
        for t in self.tracks:
            while t["votes"] and now - t["votes"][0][0] > VOTE_WINDOW_S:
                t["votes"].popleft()
            n = len(t["votes"])
            share = sum(v for _, v in t["votes"]) / n if n else 0.0
            down = n >= MIN_CHECKS and share >= VOTE_SHARE
            if not down:
                if t["down_since"] is not None and now - t["down_since"]["last"] > FORGET_S:
                    t["down_since"] = None
                continue
            if t["down_since"] is None:
                t["down_since"] = {"start": now, "last": now}
            t["down_since"]["last"] = now
            out.append({"bbox": t["box"], "share": round(share, 2), "checks": n, "fell": bool(t["fell"]),
                        "down_s": round(now - t["down_since"]["start"], 1)})
        return out
