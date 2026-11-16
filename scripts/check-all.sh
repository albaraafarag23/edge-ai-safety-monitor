#!/usr/bin/env bash
# Every check before a release or a demo, in one go. Stops at the first failure.
#
#   scripts/check-all.sh                 # unit tests, rule tests, report tests, typecheck, build
#   E2E_URL=http://localhost:3005 E2E_EMAIL=... E2E_PASSWORD=... scripts/check-all.sh
#                                        # ...plus the browser checks against a TEST copy (they change statuses)
#
# Report tests run in the ai_reporting Docker image (its Python packages), so build it first if needed:
# `docker compose build ai_reporting`.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n== %s\n' "$*"; }

step "Rule engine tests"
(cd event_engine && python3 test_rules.py | tail -1 && python3 test_demo_plugin.py | tail -1 && python3 test_hospital_plugin.py | tail -1)

step "Rule drives: what a box accepts and refuses"
(cd plugin_loader && python3 test_pack.py | tail -1)
(cd plugin_loader && python3 test_licence.py | tail -1)
# plugin_source.py is copied into each service (each builds its image from its own folder): the copies must match
for d in cv_pipeline event_engine backend ai_reporting; do
  cmp -s plugin_loader/plugin_source.py "$d/plugin_source.py" \
    || { echo "$d/plugin_source.py differs from plugin_loader/plugin_source.py: copy it over"; exit 1; }
done
echo "plugin_source.py: 4 copies identical"

step "Person tracker tests"
(cd cv_pipeline && python3 test_tracker.py | tail -1)

step "Posture tests (person down, sleeping) + every plugin loads in test mode"
(cd cv_pipeline && python3 test_posture.py | tail -1)

step "Portal tests (passkeys, approvals, roles, security log)"
# PORTAL_PYTHON: a Python with portal/requirements.txt + pytest + httpx (else a throwaway venv is made once)
PORTAL_PY=${PORTAL_PYTHON:-}
if [ -z "$PORTAL_PY" ]; then
  VENV="${XDG_CACHE_HOME:-$HOME/.cache}/sitesentry/portal-venv"
  [ -x "$VENV/bin/python" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" -q install -r portal/requirements.txt pytest httpx; }
  PORTAL_PY="$VENV/bin/python"
fi
(cd portal && "$PORTAL_PY" -m pytest -q test_portal.py 2>&1 | tail -1)

step "Report tests (ai_reporting image)"
IMAGE=$(docker compose config --images ai_reporting 2>/dev/null | grep ai_reporting | head -1)
docker run --rm -v "$PWD/ai_reporting:/app" -v "$PWD/plugins:/plugins" -e PLUGINS_DIR=/plugins -w /app "$IMAGE" \
  python test_reports.py | tail -1

step "Frontend: typecheck, unit tests, build"
(cd frontend && npm run --silent typecheck && npx vitest run 2>&1 | grep -E "Tests " && npx vite build --logLevel error && echo "build ok")

if [ -n "${E2E_URL:-}" ]; then
  step "Browser checks against $E2E_URL"
  python3 e2e/check_site.py
else
  step "Browser checks skipped (set E2E_URL, E2E_EMAIL, E2E_PASSWORD to run them against a test copy)"
fi
printf '\nAll checks passed.\n'
