#!/usr/bin/env bash
# Builds the product page on its own and publishes it to Cloudflare Pages (free, always online).
# Its "Sign in" buttons link to the console's public address (Tailscale Funnel), and it shows
# whether the live demo is up. See docs/deploy.md.
#
#   scripts/deploy-site.sh https://edge-ai-safety.your-tailnet.ts.net [pages-project-name]
#
# PAGES_BRANCH must be the project's production branch (set when the project was created),
# otherwise the upload becomes a preview and <project>.pages.dev doesn't change.
set -euo pipefail

CONSOLE_URL="${1:?Usage: $0 <console URL, e.g. https://sitesentry.tail1234.ts.net> [pages project name]}"
CONSOLE_URL="${CONSOLE_URL%/}"
PROJECT="${2:-edge-ai-safety}"
# the edge-ai-safety project was created with this production branch
BRANCH="${PAGES_BRANCH:-feature/construction-plugin-alerts}"
[[ "$CONSOLE_URL" == https://* ]] || { echo "The console URL must start with https://" >&2; exit 1; }

cd "$(dirname "$0")/../frontend"
[ -d node_modules ] || npm install

echo "Building the product page (console: $CONSOLE_URL)"
VITE_CONSOLE_URL="$CONSOLE_URL" npx vite build --outDir dist-site --emptyOutDir

# Cloudflare Pages response headers. connect-src allows the live-demo status check.
cat > dist-site/_headers <<HEADERS
/*
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' $CONSOLE_URL; font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
/assets/*
  Cache-Control: public, max-age=31536000, immutable
HEADERS

echo "Publishing to Cloudflare Pages project '$PROJECT' (production branch: $BRANCH)"
npx --yes wrangler@4 pages deploy dist-site --project-name "$PROJECT" --branch "$BRANCH" --commit-dirty=true
