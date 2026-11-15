#!/usr/bin/env bash
# One-time hardening of the Jetson, run as root from the laptop:
#   ssh -t jetson 'sudo bash ~/sitesentry/app/jetson/harden.sh'
# Safe to run again. What it does, and how to undo each step:
#   1. Keeps the GPU at its top clock (CPU and memory stay automatic), now and at every boot, so the GPU doesn't
#      slow down between frames. Not full jetson_clocks: that trips over-current protection.    Undo: gpu-clock.sh off
#   2. SSH: keys only, no passwords, no root login.    Undo: rm /etc/ssh/sshd_config.d/10-sitesentry.conf; systemctl reload ssh
#   3. Turns off rpcbind (port 111, an NFS helper this project doesn't use).    Undo: systemctl enable --now rpcbind
#   4. Firewall (ufw): nothing comes in except SSH and Tailscale. The console's ports are already bound to
#      127.0.0.1 and the public address goes out through Tailscale Funnel, so neither is affected.    Undo: ufw disable
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run with sudo"; exit 1; }
say() { echo; echo "== $*"; }

say "1. GPU clock"
[ -f /root/l4t_dfs.conf ] || jetson_clocks --store   # the automatic settings, for gpu-clock.sh to restore
bash "$(dirname "$0")/gpu-clock.sh"

say "2. SSH: keys only"
# never lock the owner out: only if this user already has a key that works
OWNER=${SUDO_USER:-gradproj}
if [ -s "/home/$OWNER/.ssh/authorized_keys" ]; then
  cat > /etc/ssh/sshd_config.d/10-sitesentry.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
  sshd -t && systemctl reload ssh && echo "Password logins off (key logins keep working)"
else
  echo "Skipped: /home/$OWNER/.ssh/authorized_keys is empty, so turning passwords off would lock you out"
fi

say "3. rpcbind off"
systemctl disable --now rpcbind.socket rpcbind.service 2>/dev/null || true
echo "rpcbind: $(systemctl is-active rpcbind 2>/dev/null || true)"

say "4. Firewall"
command -v ufw >/dev/null || { apt-get update -qq && apt-get install -y -qq ufw >/dev/null; }
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment 'ssh' >/dev/null
ufw allow in on tailscale0 comment 'tailscale' >/dev/null
ufw allow 41641/udp comment 'tailscale direct connections' >/dev/null
ufw --force enable >/dev/null
ufw status verbose | head -12

say "Done. Last step, by hand: change the sudo password (it was shared in a chat): passwd"
