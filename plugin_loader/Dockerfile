FROM python:3.12-slim

# mount / umount / blkid for the drives; filesystems come from the host's kernel
RUN apt-get update && apt-get install -y --no-install-recommends util-linux mount \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py pack.py plugin_source.py ./

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
