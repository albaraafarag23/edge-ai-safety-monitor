"""Builds the product page's "Try it yourself" scenes: real detections by models/construction_ppe.pt on public
test photos (Roboflow Construction Site Safety, CC BY 4.0), and the incident + report the system would produce.
Run again after retraining the model (from the repo root, with the training Python):

    python training/make_try_scenes.py

Writes frontend/public/edition/try-*.webp and frontend/src/content/tryScenes.json."""
import json, sys, glob
sys.path.insert(0, "ai_reporting")
from PIL import Image
from ultralytics import YOLO
from unittest import mock; sys.modules.setdefault("anthropic", mock.MagicMock())  # only the template is used
import report as R

plugin = json.load(open("plugins/construction_safety.json"))
m = YOLO("models/construction_ppe.pt")
THRESH = {"Person": 0.5, "Hardhat": 0.4, "NO-Hardhat": 0.45, "Safety Vest": 0.4, "NO-Safety Vest": 0.45, "machinery": 0.4, "vehicle": 0.4}
LABEL = {"en": {"NO-Hardhat": "No hard hat", "NO-Safety Vest": "No safety vest", "Hardhat": "Hard hat", "Safety Vest": "Safety vest",
                "machinery": "Machinery", "vehicle": "Vehicle", "Person": "Person"},
         "ar": {"NO-Hardhat": "بدون خوذة", "NO-Safety Vest": "بدون سترة", "Hardhat": "خوذة", "Safety Vest": "سترة عاكسة",
                "machinery": "آلة", "vehicle": "مركبة", "Person": "شخص"}}
SCENES = [
    ("vest", "youtube-263", None, {"event_type": "PPE_MISSING", "rule_id": "RULE_PPE_02", "severity": "HIGH",
      "missing_equipment": ["safety_vest"], "location": "Formwork area", "duration_seconds": 12.4}),
    ("hardhat", "youtube-192", None, {"event_type": "PPE_MISSING", "rule_id": "RULE_PPE_01", "severity": "HIGH",
      "missing_equipment": ["hard_hat", "safety_vest"], "location": "Site entrance", "duration_seconds": 9.0}),
    ("machinery", "youtube-126", (0, 0, 640, 520), {"event_type": "PERSON_NEAR_MACHINERY", "rule_id": "RULE_PROX_01",
      "severity": "CRITICAL", "missing_equipment": [], "location": "Earthworks", "duration_seconds": 3.2}),
]
out = []
for key, name, crop, inc in SCENES:
    path = next(p for p in glob.glob("data/construction-site-safety/test/images/*.jpg") if name in p)
    im = Image.open(path).convert("RGB")
    if crop: im = im.crop(crop)
    im.save(f"frontend/public/edition/try-{key}.webp", quality=82)
    r = m.predict(im, imgsz=960, conf=0.4, verbose=False)[0]
    W, H = im.size
    boxes = []
    for b in r.boxes:
        cls = m.names[int(b.cls)]; conf = float(b.conf)
        if cls not in THRESH or conf < THRESH[cls]: continue
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        boxes.append({"cls": cls, "label": {l: LABEL[l][cls] for l in LABEL}, "box": [round(x1/W, 4), round(y1/H, 4), round(x2/W, 4), round(y2/H, 4)],
                      "bad": cls.startswith("NO-") or (inc["event_type"] == "PERSON_NEAR_MACHINERY" and cls in ("Person", "machinery"))})
    # only the boxes that matter for this incident, so the picture stays readable
    show = {"PPE_MISSING": {"NO-Hardhat", "NO-Safety Vest", "Hardhat", "Safety Vest"},
            "PERSON_NEAR_MACHINERY": {"Person", "machinery"}}[inc["event_type"]]
    boxes = [b for b in boxes if b["cls"] in show]
    rule = next(x for x in plugin["rules"] if x["rule_id"] == inc["rule_id"])
    incident = {"event_id": f"evt_sample_{key}", "timestamp": "2026-10-11T08:14:05Z", "plugin_id": "construction_safety",
                "camera_id": "cam_01", "severity": inc["severity"], "event_type": inc["event_type"], "location": inc["location"],
                "duration_seconds": inc["duration_seconds"], "rules_violated": [f"{rule['rule_id']}: {rule.get('description', '')}"],
                "snapshot_url": "/media/snapshots/sample.jpg", "clip_url": "/media/clips/sample.mp4",
                "metadata": {"rule_id": inc["rule_id"], "missing_equipment": inc["missing_equipment"],
                             "detected_entities": sorted({b["cls"] for b in boxes})}}
    evidence = {"snapshot": True, "video_clip": True}
    scene = {"key": key, "image": f"/edition/try-{key}.webp", "width": W, "height": H, "boxes": boxes,
             "event_type": inc["event_type"], "severity": inc["severity"], "missing": inc["missing_equipment"],
             "location": inc["location"], "duration": inc["duration_seconds"], "actions": {}, "report": {}}
    for lang in ("en", "ar"):
        actions = R.approved_actions(plugin, inc["rule_id"], lang)
        scene["actions"][lang] = actions
        scene["report"][lang] = R.generate_from_template(incident, actions, evidence, lang, plugin)
    out.append(scene)
    print(key, W, H, [(b["cls"], b["bad"]) for b in boxes])
json.dump(out, open("frontend/src/content/tryScenes.json", "w"), ensure_ascii=False, indent=1)
