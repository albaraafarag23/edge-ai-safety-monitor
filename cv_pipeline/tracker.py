"""Follows each person from frame to frame on one camera, so things learned about them (who they are, from
face recognition) stay with them while they move. Boxes are matched to the previous frame's by overlap,
best match first; a person not seen for MAX_AGE_S is forgotten and would get a new number.
"""

MAX_AGE_S = 1.5
MIN_IOU = 0.2


def iou(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


class Tracker:
    def __init__(self, max_age_s: float = MAX_AGE_S, min_iou: float = MIN_IOU):
        self.max_age_s, self.min_iou = max_age_s, min_iou
        self._tracks = {}   # track id -> {"bbox", "seen"}
        self._next = 1

    def update(self, boxes: list, now: float) -> tuple[list[int], list[int]]:
        """boxes: [x1, y1, x2, y2] per person in this frame.
        Returns (the track id of each box, the ids of tracks that were just forgotten)."""
        pairs = sorted(((iou(t["bbox"], box), tid, i) for tid, t in self._tracks.items()
                        for i, box in enumerate(boxes)), reverse=True)
        ids = [0] * len(boxes)
        used = set()
        for overlap, tid, i in pairs:
            if overlap < self.min_iou:
                break
            if ids[i] or tid in used:
                continue
            ids[i] = tid
            used.add(tid)
        for i, box in enumerate(boxes):
            if not ids[i]:
                ids[i] = self._next
                self._next += 1
            self._tracks[ids[i]] = {"bbox": box, "seen": now}
        gone = [tid for tid, t in self._tracks.items() if now - t["seen"] > self.max_age_s]
        for tid in gone:
            del self._tracks[tid]
        return ids, gone
