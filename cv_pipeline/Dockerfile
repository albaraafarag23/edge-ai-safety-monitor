FROM python:3.11-slim

WORKDIR /app

# libgl1 + libglib2.0-0 are required by OpenCV (live mode only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install redis first (always needed); ultralytics only needed for live mode
RUN pip install --no-cache-dir redis>=5.0.0
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py plugin_config.py media.py .

CMD ["python", "main.py"]
