from datetime import datetime, timezone
import json
import uuid

# Simple mock rule:
# If a person is detected, create a low-severity test incident.

def process_detection_event(detection_event):
    incidents = []

    for obj in detection_event.get("objects", []):
        if obj.get("class") == "person":
            incident = {
                "incident_id": str(uuid.uuid4()),
                "timestamp_start": detection_event.get("timestamp"),
                "timestamp_end": datetime.now(timezone.utc).isoformat(),
                "camera_id": detection_event.get("camera_id"),
                "plugin_id": detection_event.get("plugin_id"),
                "event_type": "person_detected_test",
                "severity": "low",
                "zone_id": "test_zone_01",
                "objects_involved": [
                    {
                        "class": obj.get("class"),
                        "confidence": obj.get("confidence"),
                        "bbox": obj.get("bbox")
                    }
                ],
                "snapshot_path": None,
                "clip_path": None,
                "rule_triggered": "person_detected_rule",
                "metadata": {
                    "source": "laptop_simulation",
                    "model": detection_event.get("model")
                }
            }

            incidents.append(incident)

    return incidents


if __name__ == "__main__":
    sample_detection_event = {
        "detection_id": "test_detection_001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": "laptop_webcam_01",
        "plugin_id": "factory_safety",
        "model": "yolo11n",
        "objects": [
            {
                "class": "person",
                "confidence": 0.88,
                "bbox": [80.4, 167.6, 612.7, 479.8]
            }
        ]
    }

    incidents = process_detection_event(sample_detection_event)

    print(json.dumps({
        "input_detection_event": sample_detection_event,
        "generated_incidents": incidents
    }, indent=2))
