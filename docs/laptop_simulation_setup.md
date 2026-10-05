# Laptop Simulation Environment Setup

## Purpose
This setup is used to simulate the computer vision pipeline on a Linux laptop before deployment on the Jetson Orin Nano in semester 2.

## Hardware
- Laptop: Lenovo 83DV
- CPU: Intel Core i7-13650HX
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU
- RAM: 16GB

## Software
- OS: Ubuntu 22.04.5 LTS
- NVIDIA Driver: Installed and verified using nvidia-smi
- Python: 3.10
- Framework: Ultralytics
- Model: YOLO11n

## Completed Tests
1. NVIDIA GPU detected using nvidia-smi.
2. PyTorch CUDA support confirmed.
3. YOLO11n tested on a sample image.
4. YOLO11n tested on live webcam input.
5. YOLO detections were converted into structured JSON detection events.

## Evidence
A screenshot of the live webcam detection and JSON output was saved in:

docs/screenshots/

## Result
The laptop simulation environment is operational. The system can detect objects from live camera input and output structured detection JSON, which will later be used by the event engine.
