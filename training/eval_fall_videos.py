"""Person down, end to end on real videos: does "Person down" fire for a real fall, how soon, and never for everyday
activity (sitting down, picking something up, lying on a bed)?

    python training/eval_fall_videos.py --plugin construction_demo [--every 3] [--only fall-01,adl-05]

Plays each UR Fall Detection sequence (data/urfd: 30 falls + 40 everyday activities, camera parallel to the
floor, 30 fps; https://fenix.ur.edu.pl/~mkepski/ds/uf.html, CC BY-NC-SA 4.0: TEST ONLY, never trained on)
through the same pieces the box runs: the plugin's main model (upright people), its fall detector with the lying
check (cv_pipeline/falls.py, every --every frames like every_n_frames), stillness, and the real rule engine with
the plugin's person-down rules. The per-frame labels (-1 not lying, 0 falling, 1 lying) say when the fall
happened. Writes outputs/eval/fall_videos_<plugin>.json.
"""
import argparse
import csv
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cv_pipeline"))
sys.path.insert(0, str(ROOT / "event_engine"))
from falls import MAX_CANDIDATES, FallWatch, pad_cut  # noqa: E402
from plugin_config import load_plugin, model_specs  # noqa: E402
from posture import Stillness, is_lying  # noqa: E402
from rules import RuleEngine  # noqa: E402

FPS = 30
T0 = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)


def frames_of(zip_path: Path, hold_s: float = 0.0):
    """(frame number, image, held): the clip, then its last frame again for hold_s (the person stays as they
    ended: down after a fall, sitting or on the bed after an everyday activity). Held frames are identical, so
    the caller may reuse what it worked out for the last real frame."""
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".png"))
        num, img = 0, None
        for n in names:
            num = int(Path(n).stem.rsplit("-", 1)[1])
            img = cv2.imdecode(np.frombuffer(z.read(n), np.uint8), cv2.IMREAD_COLOR)
            yield num, img, False
        for k in range(1, int(hold_s * FPS) + 1):
            yield num + k, img, True


def labels(csv_path: Path) -> dict:
    out = {}
    for row in csv.reader(open(csv_path)):
        out.setdefault(row[0], {})[int(row[1])] = int(row[2])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", default="construction_demo")
    ap.add_argument("--plugins-dir", default=str(ROOT / "plugins"))
    ap.add_argument("--every", type=int, default=0, help="run the fall detector every n frames (default: plugin's)")
    ap.add_argument("--only", default="", help="comma-separated sequence names")
    ap.add_argument("--verify-at", type=float, default=None, help="override the plugin's verify_at")
    ap.add_argument("--hold", type=float, default=15.0,
                    help="seconds the last frame is held (the clips end 0.2-2 s after the person lands)")
    a = ap.parse_args()
    plugin = load_plugin(a.plugins_dir, a.plugin)
    specs = model_specs(plugin)
    main_spec = specs[0]
    fall_spec = next((s for s in specs[1:] if s.get("fall")), None)
    pose_spec = next((s for s in specs[1:] if s.get("pose")), None)   # the old way: a pose model
    spec = fall_spec or pose_spec
    fall = (fall_spec or {}).get("fall") or {}
    every = a.every or int(spec.get("every_n_frames", 1))
    verify_at = a.verify_at if a.verify_at is not None else float(fall.get("verify_at", 0.8))
    report = next(iter(spec["classes"]))
    upright = fall.get("upright_class", "person")
    # the upright people come from whichever model detects the upright class (e.g. yolo11n's "person")
    up_spec = next((s for s in specs if upright in (s.get("classes") or {})), {"model": "yolo11n.pt", "classes": {}})
    main_model = YOLO(str(ROOT / "models" / up_spec["model"]))
    det = YOLO(str(ROOT / "models" / spec["model"]))
    ver = YOLO(str(ROOT / "models" / fall["verifier"]), task="classify") if fall_spec else None
    yes = next(i for i, n in ver.names.items() if n == fall.get("verified_class", "lying")) if ver else None
    person_conf = float((up_spec["classes"].get(upright) or {}).get("confidence",
                                                                     up_spec.get("default_confidence", 0.4)))
    up_every = int(up_spec.get("every_n_frames", 1))
    det_conf = float((spec["classes"][report] or {}).get("confidence", spec.get("default_confidence", 0.4)))
    pose_rules = [r for r in plugin["rules"] if r.get("type") == "pose" and r.get("enabled", True)
                  and not r.get("planned")]
    rule_plugin = {**plugin, "rules": pose_rules}

    lab = {**labels(ROOT / "data/urfd/urfall-cam0-falls.csv"), **labels(ROOT / "data/urfd/urfall-cam0-adls.csv")}
    seqs = sorted(p for p in (ROOT / "data/urfd").glob("*-cam0-rgb.zip"))
    if a.only:
        seqs = [p for p in seqs if p.name.split("-cam0")[0] in a.only.split(",")]
    results = {}
    for zp in seqs:
        name = zp.name.split("-cam0")[0]
        engine = RuleEngine({plugin["plugin_id"]: rule_plugin}, site_tz="UTC")
        watch, still = FallWatch(), Stillness()
        last, fired, verified_yes, checks, persons = [], [], 0, 0, []
        diag = {"frames_with_box": 0, "frames_box_confirmed": 0, "reported_down": 0, "fell": None, "max_down_s": 0}
        fall_start = next((f for f, l in sorted(lab.get(name, {}).items()) if l >= 0), None)
        cache = {}   # held frames: same image, same model outputs
        for i, (num, img, held) in enumerate(frames_of(zp, a.hold)):
            t = num / FPS
            h, w = img.shape[:2]
            if i % up_every == 0:   # like the box: an extra model runs every n frames, its result reused
                if not (held and "persons" in cache):
                    people = main_model.predict(img, conf=person_conf, verbose=False)[0]
                    cache["persons"] = [b for b, c in zip(people.boxes.xyxy.tolist(), people.boxes.cls.tolist())
                                        if people.names[int(c)] == upright]
                persons = cache["persons"]
            if i % every == 0 and pose_spec and not fall_spec:   # the old pose rule, as posture.py runs it live
                if not (held and "pose" in cache):
                    r = det.predict(img, conf=det_conf, verbose=False)[0]
                    cache["pose"] = (len(r.boxes), [b for b, k in zip(r.boxes.xyxy.tolist(), r.keypoints.data.tolist())
                                                    if is_lying(b, k)])
                n_people, lying_boxes = cache["pose"]
                checks += n_people
                verified_yes += len(lying_boxes)
                last = [{"class_name": report, "confidence": 0.9, "bbox": b, "attributes": {}} for b in lying_boxes]
                for d, s in zip(last, still.update([d["bbox"] for d in last], now=t)):
                    d["attributes"]["still_s"] = round(s)
            elif i % every == 0:
                if not (held and "cands" in cache):
                    r = det.predict(img, conf=det_conf, verbose=False)[0]
                    cache["cands"] = []
                    for box, conf in sorted(zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()), key=lambda b: -b[1])[:MAX_CANDIDATES]:
                        patch = pad_cut(img, box)
                        ok = False
                        if patch is not None:
                            p = float(ver.predict(patch, imgsz=int(fall.get("verifier_imgsz", 224)), verbose=False)[0].probs.data[yes])
                            ok = p >= verify_at
                        cache["cands"].append((box, ok))
                cands = cache["cands"]
                if held:   # the person as they ended up (down after a fall)
                    diag["frames_with_box"] += bool(cands)
                    diag["frames_box_confirmed"] += any(ok for _, ok in cands)
                checks += len(cands)
                verified_yes += sum(ok for _, ok in cands)
                down = watch.update(t, cands)
                if down:
                    diag["reported_down"] += 1
                    diag["fell"] = diag["fell"] or any(d["fell"] for d in down)
                    diag["max_down_s"] = max(diag["max_down_s"], max(d["down_s"] for d in down))
                last = [{"class_name": report, "confidence": d["share"], "bbox": d["bbox"],
                         "attributes": {"fell": d["fell"], "down_s": d["down_s"], "checks": d["checks"]}} for d in down]
                for d, s in zip(last, still.update([d["bbox"] for d in last], now=t)):
                    d["attributes"]["still_s"] = round(s)
            watch.note_people(t, persons)
            dets = [{"class_name": upright, "confidence": 0.9, "bbox": b} for b in persons] + last
            event = {"timestamp": (T0 + timedelta(seconds=t)).isoformat(), "camera_id": "cam_01", "frame_id": num,
                     "plugin_id": plugin["plugin_id"], "frame_size": [w, h], "detections": dets}
            for inc in engine.process(event):
                fired.append({"rule": inc["metadata"]["rule_id"], "frame": num, "t": round(t, 2),
                              "fell": any((o.get("attributes") or {}).get("fell") for o in last)})
        down_alarm = [f for f in fired if f["rule"] == "RULE_POSE_01"]
        results[name] = {"fall_start_frame": fall_start, "alarms": fired,
                         "first_down_alarm_s_after_fall": round(down_alarm[0]["t"] - fall_start / FPS, 2)
                         if down_alarm and fall_start else None,
                         "checks": checks, "check_said_lying": verified_yes, "diag": diag}
        kind = "FALL" if name.startswith("fall") else "adl "
        print(f"{kind} {name}: {'ALARM' if down_alarm else 'no alarm'}"
              + (f" {results[name]['first_down_alarm_s_after_fall']} s after the fall began" if down_alarm and fall_start else "")
              + (f" (seen fall: {down_alarm[0]['fell']})" if down_alarm else "")
              + f"; checks {verified_yes}/{checks} said lying; held: box {diag['frames_with_box']}, confirmed "
              f"{diag['frames_box_confirmed']}, down reported {diag['reported_down']}, fell {diag['fell']}, "
              f"down {diag['max_down_s']} s", flush=True)
    falls = [n for n in results if n.startswith("fall")]
    adls = [n for n in results if n.startswith("adl")]
    caught = [n for n in falls if any(f["rule"] == "RULE_POSE_01" for f in results[n]["alarms"])]
    false = [n for n in adls if any(f["rule"] == "RULE_POSE_01" for f in results[n]["alarms"])]
    delays = sorted(results[n]["first_down_alarm_s_after_fall"] for n in caught
                    if results[n]["first_down_alarm_s_after_fall"] is not None)
    summary = {"plugin": a.plugin, "every": every, "verify_at": verify_at,
               "falls_caught": f"{len(caught)}/{len(falls)}", "adl_false_alarms": f"{len(false)}/{len(adls)}",
               "false_alarm_sequences": false,
               "delay_median_s": delays[len(delays) // 2] if delays else None}
    print(json.dumps(summary, indent=1))
    out = ROOT / f"outputs/eval/fall_videos_{a.plugin}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "sequences": results}, indent=1))


if __name__ == "__main__":
    main()
