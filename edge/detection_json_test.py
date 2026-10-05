from ultralytics import YOLO
from datetime import datetime, timezone
import json
import uuid

model = YOLO("yolo11n.pt")

results = model.predict(
    source=0,
    show=True,
    save=False,
    conf=0.4,
    stream=True
)

for result in results:
    objects = []

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = model.names[class_id]
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()

        objects.append({
            "class": class_name,
            "confidence": round(confidence, 3),
            "bbox": [
                round(x1, 1),
                round(y1, 1),
                round(x2, 1),
                round(y2, 1)
            ]
        })

    detection_event = {
        "detection_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": "laptop_webcam_01",
        "plugin_id": "factory_safety",
        "model": "yolo11n",
        "objects": objects
    }

    print(json.dumps(detection_event, indent=2))
