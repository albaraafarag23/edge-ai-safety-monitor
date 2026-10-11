#!/usr/bin/env bash
# Keeps the public console (Tailscale Funnel) reachable. Run every 5 minutes from cron:
#   */5 * * * * /home/albaraa/edge-ai-safety-monitor/scripts/funnel-watchdog.sh
#
# Why: after a reboot (2026-10-11) the console was fine locally and `tailscale funnel status` said "on", but the
# public DNS record was gone, so the product page showed "Live demo offline" until Funnel was switched on again.
# A check from this laptop must go over the public internet: the laptop's own DNS (MagicDNS) answers with the
# Tailscale address and would say all is well. Needs `sudo tailscale set --operator=$USER` once (done).
set -u

HOST="${FUNNEL_HOST:-edge-ai-safety.tail1de778.ts.net}"
TARGET="${FUNNEL_TARGET:-http://127.0.0.1:3000}"
STATE_DIR="${STATE_DIR:-$HOME/.local/state/sitesentry}"
LOG="$STATE_DIR/funnel-watchdog.log"
FAILS="$STATE_DIR/funnel-fails"
mkdir -p "$STATE_DIR"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; }

# Nothing to publish if the console itself is down (Docker restarts it; not this script's job)
if ! curl -fs -m 10 -o /dev/null "$TARGET/api/health"; then
    log "console not answering locally at $TARGET, skipping"
    exit 0
fi
# No internet: nothing can be checked or fixed
if ! curl -fs -m 10 -o /dev/null https://1.1.1.1; then
    exit 0
fi

problem=""
ip=$(dig +short +time=5 +tries=2 @1.1.1.1 "$HOST" A | grep -E '^[0-9.]+$' | head -1)
if [ -z "$ip" ]; then
    problem="no public DNS record"
elif ! curl -fs -m 20 -o /dev/null --resolve "$HOST:443:$ip" "https://$HOST/api/health"; then
    problem="public address $ip not answering"
fi

if [ -z "$problem" ]; then
    [ -s "$FAILS" ] && log "OK again"
    : > "$FAILS"
    exit 0
fi

# Act on the second failed check in a row, so a passing blip doesn't trigger anything
echo x >> "$FAILS"
n=$(wc -l < "$FAILS")
log "check failed ($problem), $n in a row"
if [ "$n" -ge 2 ]; then
    if out=$(tailscale funnel --bg "$TARGET" 2>&1); then
        log "switched Funnel on again"
    else
        log "could not switch Funnel on: $out"
    fi
fi
if [ "$n" -ge 6 ]; then
    log "still failing after 30 min; may need: sudo systemctl restart tailscaled"
fi
