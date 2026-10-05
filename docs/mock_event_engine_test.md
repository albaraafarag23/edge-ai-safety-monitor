# Mock Event Engine Test

## Purpose
This test validates the second stage of the project pipeline: converting object detection events into structured incident events.

## Pipeline Stage
Detection JSON -> Event Engine Rules -> Incident JSON

## Input
The mock event engine receives a detection event containing:
- detection ID
- timestamp
- camera ID
- plugin ID
- model name
- detected objects with class, confidence, and bounding box

## Rule Used
A simple test rule was implemented:

If the detected object class is `person`, generate a test incident.

## Output
The event engine generates a structured incident event containing:
- incident ID
- start and end timestamps
- camera ID
- plugin ID
- event type
- severity
- zone ID
- objects involved
- triggered rule
- metadata

## Result
The mock event engine successfully converted a detection JSON into an incident JSON. This confirms the connection between the computer vision pipeline and the event engine layer.

## Output File
The generated test output was saved in:

outputs/mock_incident_output.json
