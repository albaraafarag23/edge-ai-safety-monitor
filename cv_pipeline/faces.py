"""Face recognition: puts a name on the people the detector sees, from photos enrolled per person.

Enrolled photos live in FACES_DIR, one folder per person (the console's People page writes them; they can
also be copied in by hand):

    faces/<person_id>/person.json     {"name": "Albaraa Farag", "name_ar": "..."}   (optional; else the folder name)
    faces/<person_id>/<anything>.jpg  5-10 photos of that person (docs/faces.md says which)

Two models, both ONNX files in MODELS_DIR (scripts/get-face-models.sh downloads them):
  - YuNet finds the face and its eyes, nose and mouth corners (OpenCV's own detector)
  - ArcFace (ResNet-50, WebFace600K) turns the aligned 112x112 face into 512 numbers; two faces of the same
    person give nearly the same numbers (cosine similarity), run with onnxruntime, or OpenCV if it is missing

It runs in its own thread and never slows detection down: the detector loop hands over a person now and
then (FaceIdentifier.observe), the thread reads the face from the full-resolution frame and votes. A name
is given after one strong match or two normal ones on the same tracked person, and then stays with that
person (tracker.py) while they are in view, also when they turn away. A clear face that matches nobody
after a few looks is reported as unknown.

The thread also keeps the gallery up to date (new photos are picked up within seconds) and tells the console
through Redis how each photo did: `faces:photos` (hash "<person_id>/<file>" -> JSON) and `faces:state`.
Without the model files, or with FACE_RECOGNITION=off, everything here is skipped.
"""
import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import redis

FACES_DIR = os.getenv("FACES_DIR", "../faces")
MODELS_DIR = os.getenv("MODELS_DIR", "../models")
DET_MODEL = os.getenv("FACE_DET_MODEL") or str(Path(MODELS_DIR) / "face_detection_yunet_2023mar.onnx")
REC_MODEL = os.getenv("FACE_REC_MODEL") or str(Path(MODELS_DIR) / "w600k_r50.onnx")
SWITCH = os.getenv("FACE_RECOGNITION", "auto").lower()       # auto = on when the models are there; off
DEVICE = os.getenv("FACE_DEVICE", "cpu").lower()             # cpu | cuda (onnxruntime with CUDA only)
THREADS = int(os.getenv("FACE_THREADS", "2"))

# cosine similarity between a seen face and a person's enrolled photos (measured: docs/faces.md)
MATCH = float(os.getenv("FACE_MATCH", "0.38"))               # counts as a vote for that person
STRONG = float(os.getenv("FACE_STRONG", "0.50"))             # enough on its own
MARGIN = 0.05                                                # ahead of the next most similar person by this much
VOTES = 2
MIN_FACE_PX = int(os.getenv("FACE_MIN_PX", "28"))            # narrower faces (far away) are not judged
UNKNOWN_AFTER = 4                                            # clear looks without a match before "unknown"
RETRY_S, RECHECK_S = 0.4, 3.0                                # look again: while unnamed / once settled
RELOAD_S = 5.0
STATE_TTL_S = 30

ENROL_MIN_FACE_PX = 80
ENROL_MIN_SCORE = 0.8
ODD_ONE_OUT = 0.25                                           # a photo this unlike the person's others is left out
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PHOTOS_KEY, STATE_KEY = "faces:photos", "faces:state"

# where the eyes, nose and mouth corners sit in the 112x112 picture ArcFace was trained on
ARCFACE_POINTS = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                           [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)


@dataclass
class Face:
    box: tuple                 # x, y, w, h in image pixels
    points: np.ndarray         # 5x2: right eye, left eye, nose, right and left mouth corner (the person's)
    score: float

    @property
    def turned(self) -> float:
        """0 = facing the camera, towards 1 = in profile (how far the nose sits from the middle of the eyes)."""
        eyes = np.linalg.norm(self.points[1] - self.points[0])
        return float(abs(self.points[2][0] - (self.points[0][0] + self.points[1][0]) / 2) / eyes) if eyes else 1.0


class FaceEngine:
    """Detects faces and turns them into embeddings. Not thread-safe: one thread uses it."""

    def __init__(self, det_model: str = DET_MODEL, rec_model: str = REC_MODEL, device: str = DEVICE):
        self.detector = cv2.FaceDetectorYN.create(det_model, "", (320, 320), 0.6, 0.3, 50)
        self._session = self._net = None
        try:
            import onnxruntime as ort
            wanted = (["CUDAExecutionProvider"] if device == "cuda" else []) + ["CPUExecutionProvider"]
            providers = [p for p in wanted if p in ort.get_available_providers()]
            options = ort.SessionOptions()
            options.log_severity_level = 3
            options.intra_op_num_threads = THREADS   # leave the other cores to the cameras and the detector
            self._session = ort.InferenceSession(rec_model, options, providers=providers)
            self._input = self._session.get_inputs()[0].name
            self.name = f"ArcFace R50, onnxruntime {self._session.get_providers()[0].removesuffix('ExecutionProvider')}"
        except ImportError:
            self._net = cv2.dnn.readNetFromONNX(rec_model)
            self.name = "ArcFace R50, OpenCV CPU"

    def detect(self, image, max_side: int = 640) -> list[Face]:
        h, w = image.shape[:2]
        scale = min(1.0, max_side / max(h, w))
        small = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale)))) if scale < 1 else image
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, found = self.detector.detect(small)
        faces = []
        for row in found if found is not None else []:
            row = row / scale
            faces.append(Face(tuple(row[:4]), row[4:14].reshape(5, 2).astype(np.float32), float(row[14]) * scale))
        return faces

    def align(self, image, face: Face):
        matrix, _ = cv2.estimateAffinePartial2D(face.points, ARCFACE_POINTS, method=cv2.LMEDS)
        return None if matrix is None else cv2.warpAffine(image, matrix, (112, 112), borderValue=0)

    def embed(self, aligned: list) -> np.ndarray:
        """One unit-length row of 512 numbers per aligned 112x112 face."""
        blob = cv2.dnn.blobFromImages(aligned, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        out = []
        for one in blob:   # the model takes one face at a time
            if self._session is not None:
                out.append(self._session.run(None, {self._input: one[None]})[0][0])
            else:
                self._net.setInput(one[None])
                out.append(self._net.forward()[0].copy())
        out = np.array(out)
        return out / np.linalg.norm(out, axis=1, keepdims=True)


def enrol_photo(engine: FaceEngine, path: Path) -> tuple[np.ndarray | None, dict]:
    """(embedding or None, what the console shows for this photo)."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None, {"ok": False, "problem": "unreadable"}
    # a face filling the whole photo (a selfie) is found more reliably in a smaller copy
    faces = engine.detect(image, 640) or engine.detect(image, 320)
    faces = [f for f in faces if f.score >= 0.6]
    if not faces:
        return None, {"ok": False, "problem": "no_face"}
    faces.sort(key=lambda f: f.box[2], reverse=True)
    face = faces[0]
    info = {"face_px": int(face.box[2])}
    if len(faces) > 1 and faces[1].box[2] > 0.6 * face.box[2]:
        return None, {"ok": False, "problem": "several_faces", **info}
    if face.box[2] < ENROL_MIN_FACE_PX:
        return None, {"ok": False, "problem": "small_face", **info}
    if face.score < ENROL_MIN_SCORE or face.turned > 0.75:
        return None, {"ok": False, "problem": "unclear_face", **info}
    aligned = engine.align(image, face)
    if aligned is None:
        return None, {"ok": False, "problem": "unclear_face", **info}
    # the photo and its mirror image together: a little steadier than the photo alone
    pair = engine.embed([aligned, cv2.flip(aligned, 1)]).sum(axis=0)
    return pair / np.linalg.norm(pair), {"ok": True, "problem": None, **info}


def person_names(folder: Path) -> dict:
    names = {"person_id": folder.name, "person_name": folder.name.replace("_", " ").replace("-", " ").title()}
    try:
        meta = json.loads((folder / "person.json").read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            if str(meta.get("name") or "").strip():
                names["person_name"] = str(meta["name"]).strip()[:100]
            if str(meta.get("name_ar") or "").strip():
                names["person_name_ar"] = str(meta["name_ar"]).strip()[:100]
    except (OSError, ValueError):
        pass
    return names


class Gallery:
    """Everyone's enrolled embeddings. Photos already read are kept, so a new photo costs one face, not all."""

    def __init__(self, engine: FaceEngine, faces_dir: str = FACES_DIR):
        self.engine, self.dir = engine, Path(faces_dir)
        self._cache = {}                     # (path, mtime, size) -> (embedding | None, info)
        self._signature = None
        self.people: list[dict] = []         # person_names() of everyone with at least one usable photo
        self.matrix = np.zeros((0, 512), np.float32)
        self.owner = np.zeros(0, int)        # row of matrix -> index in people
        self.photos: dict[str, dict] = {}    # "<person_id>/<file>" -> info for the console

    def _scan(self) -> dict:
        found = {}
        if not self.dir.is_dir():
            return found
        for folder in sorted(p for p in self.dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            files = []
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in IMAGE_TYPES and not f.name.startswith("."):
                    try:
                        stat = f.stat()
                    except OSError:
                        continue
                    files.append((str(f), stat.st_mtime_ns, stat.st_size))
            try:
                meta = (folder / "person.json").stat().st_mtime_ns
            except OSError:
                meta = 0
            found[folder] = (meta, files)
        return found

    def refresh(self) -> bool:
        """Re-reads the folder; True if anything changed."""
        found = self._scan()
        signature = {str(folder): entry for folder, entry in found.items()}
        if signature == self._signature:
            return False
        self._signature = signature
        people, rows, owner, photos, cache = [], [], [], {}, {}
        for folder, (_, files) in found.items():
            good = []
            for key in files:
                if key not in self._cache:
                    self._cache[key] = enrol_photo(self.engine, Path(key[0]))
                cache[key] = self._cache[key]
                embedding, info = cache[key]
                label = f"{folder.name}/{Path(key[0]).name}"
                photos[label] = dict(info)
                if embedding is not None:
                    good.append((label, embedding))
            # a photo unlike the person's other photos is probably someone else: leave it out
            if len(good) >= 3:
                for label, embedding in list(good):
                    others = np.mean([e for other, e in good if other != label], axis=0)
                    if float(embedding @ (others / np.linalg.norm(others))) < ODD_ONE_OUT:
                        photos[label] = {**photos[label], "ok": False, "problem": "different_person"}
                        good = [(other, e) for other, e in good if other != label]
            if not good:
                continue
            centre = np.mean([e for _, e in good], axis=0)
            rows += [e for _, e in good] + [centre / np.linalg.norm(centre)]
            owner += [len(people)] * (len(good) + 1)
            people.append({**person_names(folder), "photos": len(good)})
        self._cache = cache
        self.people, self.photos = people, photos
        self.matrix = np.array(rows, np.float32).reshape(-1, 512)
        self.owner = np.array(owner, int)
        return True

    def match(self, embedding) -> tuple[dict | None, float, float, np.ndarray]:
        """(most similar person, their similarity, the next person's similarity, everyone's similarity in the
        order of `people`)."""
        if not self.people:
            return None, 0.0, 0.0, np.zeros(0)
        sims = self.matrix @ embedding
        best = np.full(len(self.people), -1.0)
        np.maximum.at(best, self.owner, sims)
        order = np.argsort(best)[::-1]
        second = float(best[order[1]]) if len(order) > 1 else 0.0
        return self.people[int(order[0])], float(best[order[0]]), second, best


def head_region(bbox, width: int, height: int) -> tuple[int, int, int, int]:
    """The part of a person box where the face is: the top of a standing person, most of a close-up."""
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    h = min(h, max(0.4 * h, 1.1 * w))
    pad = 0.1 * w
    return (int(max(x1 - pad, 0)), int(max(y1 - pad, 0)), int(min(x2 + pad, width)), int(min(y1 + h, height)))


@dataclass
class _Track:
    votes: dict = field(default_factory=dict)    # person_id -> matches so far
    looks: int = 0                               # clear faces judged
    doubts: int = 0                              # clear faces in a row that didn't look like `person`
    person: dict | None = None
    score: float = 0.0
    unknown: bool = False
    pending: bool = False
    next_try: float = 0.0


class FaceIdentifier:
    def __init__(self, redis_url: str):
        self.enabled = False
        self.status = "switched off (FACE_RECOGNITION=off)"
        if SWITCH == "off":
            return
        missing = [p for p in (DET_MODEL, REC_MODEL) if not os.path.isfile(p)]
        if missing:
            self.status = f"off: model file(s) not found: {', '.join(missing)} (scripts/get-face-models.sh)"
            return
        try:
            self.engine = FaceEngine()
        except Exception as e:   # a broken model file must not stop detection
            self.status = f"off: could not load the face models ({e})"
            return
        self.gallery = Gallery(self.engine)
        self.enabled = True
        self.status = f"on ({self.engine.name}), photos in {FACES_DIR}"
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._jobs = queue.Queue(maxsize=4)
        self._tracks: dict[tuple, _Track] = {}
        self._lock = threading.Lock()
        self._known = False          # whether anyone is enrolled (read by the detector loop)
        self._unpublished = True     # photo results not yet sent to Redis
        threading.Thread(target=self._run, daemon=True, name="faces").start()

    # ---------- called by the detector loop (must stay cheap) ----------
    def observe(self, camera_id: str, track_id: int, frame, bbox, now: float):
        """A tracked person in this frame. Hands the frame to the face thread when it is time for another look."""
        if not self.enabled or not self._known:
            return
        with self._lock:
            track = self._tracks.setdefault((camera_id, track_id), _Track())
            if track.pending or now < track.next_try:
                return
            track.pending = True
        try:
            self._jobs.put_nowait((camera_id, track_id, frame, bbox))
        except queue.Full:
            with self._lock:
                track.pending = False

    def identity(self, camera_id: str, track_id: int) -> dict:
        """Attributes for this person's detection: who they are, or that they are unknown; {} while undecided."""
        if not self.enabled:
            return {}
        with self._lock:
            track = self._tracks.get((camera_id, track_id))
            if track is None:
                return {}
            if track.person:
                return {"identity": "known", **{k: v for k, v in track.person.items() if k != "photos"},
                        "face_score": round(track.score, 2)}
            return {"identity": "unknown"} if track.unknown else {}

    def forget(self, camera_id: str, track_ids: list[int]):
        if self.enabled and track_ids:
            with self._lock:
                for tid in track_ids:
                    self._tracks.pop((camera_id, tid), None)

    # ---------- the face thread ----------
    def _run(self):
        last_reload = 0.0
        while True:
            if time.monotonic() - last_reload >= RELOAD_S:
                last_reload = time.monotonic()
                try:
                    self._reload()
                except Exception as e:
                    print(f"[CV] Faces: could not refresh the enrolled photos ({e})", flush=True)
            try:
                job = self._jobs.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._look(*job)
            except Exception as e:   # one odd frame must not stop recognition
                print(f"[CV] Faces: {e}", flush=True)
                self._settle(job[0], job[1], RETRY_S)

    def _reload(self):
        changed = self.gallery.refresh()
        self._unpublished |= changed
        if changed:
            g = self.gallery
            self._known = bool(g.people)
            with self._lock:   # names may have changed or people been removed: decide again
                self._tracks.clear()
            bad = sum(1 for p in g.photos.values() if not p["ok"])
            print(f"[CV] Faces: {len(g.people)} enrolled, {len(g.photos) - bad} photo(s) in use"
                  + (f", {bad} photo(s) not usable (see the console's People page)" if bad else ""), flush=True)
        try:
            pipe = self._redis.pipeline()
            if self._unpublished:   # also after Redis was away when the photos changed
                pipe.delete(PHOTOS_KEY)
                if self.gallery.photos:
                    pipe.hset(PHOTOS_KEY, mapping={k: json.dumps(v) for k, v in self.gallery.photos.items()})
            pipe.set(STATE_KEY, json.dumps({
                "engine": self.engine.name, "people": len(self.gallery.people), "photos": len(self.gallery.photos),
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }), ex=STATE_TTL_S)
            pipe.execute()
            self._unpublished = False
        except redis.exceptions.RedisError:
            pass   # the console's People page catches up when Redis is back

    def _settle(self, camera_id, track_id, wait: float):
        with self._lock:
            track = self._tracks.get((camera_id, track_id))
            if track:
                track.pending = False
                track.next_try = time.time() + wait

    def _look(self, camera_id, track_id, frame, bbox):
        image = frame.full()
        x1, y1, x2, y2 = head_region(bbox, image.shape[1], image.shape[0])
        if x2 - x1 < MIN_FACE_PX or y2 - y1 < MIN_FACE_PX:
            return self._settle(camera_id, track_id, RETRY_S)
        crop = image[y1:y2, x1:x2]
        faces = [f for f in self.engine.detect(crop, 320) if f.score >= 0.7]
        face = max(faces, key=lambda f: f.box[2], default=None)
        if face is None or face.box[2] < MIN_FACE_PX or face.turned > 0.75:
            return self._settle(camera_id, track_id, RETRY_S)   # no face, too far or turned away: look again soon
        aligned = self.engine.align(crop, face)
        if aligned is None:
            return self._settle(camera_id, track_id, RETRY_S)
        person, score, second, everyone = self.gallery.match(self.engine.embed([aligned])[0])

        with self._lock:
            track = self._tracks.get((camera_id, track_id))
            if track is None:
                return
            track.pending = False
            track.looks += 1
            if track.person:
                # still them? Two clear faces in a row that aren't: someone else now stands where they were
                # (people crossing can swap tracks), so start over rather than keep a wrong name
                now_at = next((i for i, p in enumerate(self.gallery.people)
                               if p["person_id"] == track.person["person_id"]), None)
                track.doubts = 0 if now_at is not None and everyone[now_at] >= MATCH else track.doubts + 1
                if track.doubts >= 2:
                    print(f"[CV] Faces: {camera_id} person {track_id} is no longer {track.person['person_name']}",
                          flush=True)
                    track.person, track.votes, track.looks, track.doubts, track.score = None, {}, 1, 0, 0.0
            clear = person is not None and score - second >= MARGIN
            if clear and score >= MATCH:
                pid = person["person_id"]
                track.votes[pid] = track.votes.get(pid, 0) + 1
                if score >= STRONG or track.votes[pid] >= VOTES:
                    if track.person is None or track.person["person_id"] != pid:
                        print(f"[CV] Faces: {camera_id} person {track_id} is {person['person_name']} "
                              f"({score:.2f})", flush=True)
                        track.votes, track.score = {pid: track.votes[pid]}, 0.0
                    track.person, track.unknown = person, False
                    track.score = max(score, track.score)
            elif track.person is None and not track.votes and track.looks >= UNKNOWN_AFTER:
                track.unknown = True
            track.next_try = time.time() + (RECHECK_S if track.person or track.unknown else RETRY_S)
