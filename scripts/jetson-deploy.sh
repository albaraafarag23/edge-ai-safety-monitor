#!/usr/bin/env bash
# Puts this working tree on the Jetson and restarts the stack there, then checks it.
#   scripts/jetson-deploy.sh            (needs `ssh jetson` to work: see jetson/README.md)
#
# Copies code only: never .env, data, outputs, models, media or CLAUDE.md (the Jetson keeps its own). Face photos
# (faces/) are copied, since they are what the People page shows. If the laptop's .env has a GEMINI_API_KEY
# (reports by Gemini) or DEMO_EMAIL / DEMO_PASSWORD (the read-only demo account, docs/deploy.md) and the
# Jetson's doesn't, they are added there.
set -euo pipefail
cd "$(dirname "$0")/.."
APP="sitesentry/app"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.jetson.yml"

echo "== Jetson reachable?"
ssh -o ConnectTimeout=8 jetson true

echo "== Copying code"
rsync -az \
  --exclude .git --exclude data --exclude outputs --exclude models --exclude media --exclude runs \
  --exclude 'CLAUDE.md' --exclude 'docker-compose.override.yml' --exclude '.env' --exclude '.env.*' \
  --exclude node_modules --exclude dist --exclude dist-site --exclude faces --exclude config/cameras.json \
  --exclude '__pycache__' --exclude '*.pt' --exclude '*.engine' --exclude '*.onnx' \
  ./ "jetson:$APP/"

echo "== Copying face photos"
rsync -az faces/ "jetson:$APP/faces/"

# settings the Jetson takes from the laptop when it has none of its own (values are never printed)
for name in GEMINI_API_KEY DEMO_EMAIL DEMO_PASSWORD; do
  if grep -qE "^$name=.+" .env 2>/dev/null; then
    if ssh jetson "grep -qE '^$name=.+' $APP/.env"; then
      echo "== $name: already on the Jetson"
    else
      echo "== $name: adding the laptop's to the Jetson's .env"
      grep -E "^$name=" .env | ssh jetson "cat >> $APP/.env"
    fi
  fi
done

echo "== Rebuilding and restarting (a few minutes the first time)"
ssh jetson "cd $APP && $COMPOSE up -d --build --remove-orphans 2>&1 | grep -E 'Started|Error|error' | tail -15"

echo "== Checking"
sleep 20
ssh jetson "cd $APP && $COMPOSE ps --format '{{.Name}}: {{.Status}}'"
ssh jetson "cd $APP && $COMPOSE logs --since 2m cv_pipeline 2>&1 | grep -E 'LIVE MODE|Face recognition|Faces:|Media recorder|Error|Traceback' | tail -8"
ssh jetson "cd $APP && $COMPOSE logs --since 2m ai_reporting live backend 2>&1 | grep -E 'Ready|Live view process|startup complete|Error|Traceback' | tail -6"
ssh jetson "curl -s -o /dev/null -w 'console on the Jetson: %{http_code}\n' http://127.0.0.1:3000/api/health"
