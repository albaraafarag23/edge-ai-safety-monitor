# The portal: screens (frontend, portal build) + server, one image. Built from the repository root:
#   docker build -f portal/Dockerfile -t sitesentry-portal .
# Render builds it the same way (render.yaml). Only frontend/ and portal/ are sent (portal/Dockerfile.dockerignore).

FROM node:20-slim AS screens
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build:portal

FROM python:3.11-slim
WORKDIR /app
COPY portal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY portal/*.py ./
COPY --from=screens /ui/dist-portal ./ui
ENV PORTAL_UI_DIR=/app/ui
USER 1000:1000
# Render sets PORT; behind its proxy, the visitor's address comes in X-Forwarded-For
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8010} --proxy-headers --forwarded-allow-ips='*'"]
