#!/usr/bin/env bash
set -Eeuo pipefail
REPO_DIR="${SB_SYNC_REPO_DIR:-/opt/superbajaar/source}"
SYSTEMD_DIR="/etc/systemd/system"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
[[ -f "$REPO_DIR/backend/scripts/sync_main.sh" ]] || { echo "Sync script missing from $REPO_DIR" >&2; exit 1; }
[[ -d "$REPO_DIR/.git" ]] || { echo "Git checkout missing at $REPO_DIR" >&2; exit 1; }
install -o root -g root -m 0644 "$REPO_DIR/deploy/systemd/superbajaar-github-sync.service" "$SYSTEMD_DIR/superbajaar-github-sync.service"
install -o root -g root -m 0644 "$REPO_DIR/deploy/systemd/superbajaar-github-sync.timer" "$SYSTEMD_DIR/superbajaar-github-sync.timer"
touch /var/log/superbajaar-github-sync.log
chown ubuntu:ubuntu /var/log/superbajaar-github-sync.log
chmod 0644 /var/log/superbajaar-github-sync.log
systemctl daemon-reload
systemctl enable --now superbajaar-github-sync.timer
systemctl start superbajaar-github-sync.service
systemctl --no-pager --full status superbajaar-github-sync.timer
