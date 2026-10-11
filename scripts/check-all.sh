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
(cd event_engine && python3 test_rules.py | tail -1)

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
