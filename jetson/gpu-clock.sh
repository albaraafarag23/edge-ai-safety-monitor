#!/usr/bin/env bash
# Gives the GPU a minimum clock (default 714 MHz) so it stays fast between frames; CPU and memory stay automatic.
#   ssh -t jetson 'sudo bash ~/sitesentry/app/jetson/gpu-clock.sh'          (on at 714 MHz; also at every boot)
#   ssh -t jetson 'sudo bash ~/sitesentry/app/jetson/gpu-clock.sh 612'      (another floor, in MHz)
#   ssh -t jetson 'sudo bash ~/sitesentry/app/jetson/gpu-clock.sh off'      (back to automatic)
# Why: the GPU lowers its clock while it waits between camera frames, so each frame then takes 21 ms instead of
# 8 ms and the detector falls behind the camera. Full jetson_clocks (GPU + CPU + memory all pinned) fixed that but
# set off the board's over-current protection (2026-11-15: 31 events in ~2 min at 25 W), and so did the GPU alone
# at its top 918 MHz (spikes on the GPU rail at only ~12 W total). So the GPU gets a floor below its top instead:
# it can't drop to 306 MHz between frames, and it can still go higher when it needs to.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run with sudo"; exit 1; }
GPU=/sys/devices/platform/bus@0/17000000.gpu/devfreq/17000000.gpu
UNIT=/etc/systemd/system/jetson-clocks.service

# undo full jetson_clocks first (saved by harden.sh), then drop its boot service
[ -f /root/l4t_dfs.conf ] && jetson_clocks --restore /root/l4t_dfs.conf || true
systemctl disable jetson-clocks.service >/dev/null 2>&1 || true
rm -f "$UNIT"

ARG=${1:-714}
if [ "$ARG" = off ]; then
  systemctl disable --now gpu-clock.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/gpu-clock.service
  cat "$GPU/available_frequencies" | tr ' ' '\n' | head -1 > "$GPU/min_freq"
  systemctl daemon-reload
  echo "GPU clock automatic again: $(( $(cat $GPU/cur_freq) / 1000000 )) MHz now"
  exit 0
fi

[[ "$ARG" =~ ^[0-9]+$ ]] || { echo "Give a speed in MHz, or off"; exit 1; }
HZ=$((ARG * 1000000))
grep -qw "$HZ" "$GPU/available_frequencies" || { echo "Not a GPU speed. Choose from: $(sed 's/000000//g' $GPU/available_frequencies)"; exit 1; }
cat > /etc/systemd/system/gpu-clock.service <<EOF
[Unit]
Description=Minimum GPU clock for the SiteSentry detector
After=nvpmodel.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 20
ExecStart=/bin/sh -c 'echo $HZ > $GPU/min_freq'

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable gpu-clock.service >/dev/null
echo "$HZ" > "$GPU/min_freq"
echo "GPU floor $ARG MHz (now $(( $(cat $GPU/cur_freq) / 1000000 )) MHz); CPU and memory automatic. On at every boot."
