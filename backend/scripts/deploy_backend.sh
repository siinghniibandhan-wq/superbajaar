#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${SB_DEPLOY_REPO_DIR:-/opt/superbajaar/source}"
SERVICE="${SB_DEPLOY_SERVICE:-superbajaar-backend.service}"
HEALTH_URL="${SB_DEPLOY_HEALTH_URL:-https://superappkart.duckdns.org/api/health}"
HR_ROUTE="${SB_DEPLOY_HR_ROUTE:-https://superappkart.duckdns.org/api/hr/attendance/corrections?status=pending}"
TARGET_SHA="${1:?Usage: deploy_backend.sh <commit-sha>}"
# Shared with sync_main.sh: serialize source checkout updates and deployments.
# Reuse the lock already used by the installed two-minute sync timer.
LOCK_FILE="${SB_DEPLOY_LOCK_FILE:-/run/lock/superbajaar-github-sync.lock}"
log(){ printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"; }
fail(){ log "ERROR: $*"; exit 1; }
[[ "$(id -un)" == ubuntu ]] || fail "Run as ubuntu; do not run as root"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid commit SHA"
[[ -d "$REPO_DIR/.git" ]] || fail "Repository missing: $REPO_DIR"
command -v flock >/dev/null && command -v curl >/dev/null && command -v git >/dev/null || fail "Required command missing"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -w 120 9 || fail "Timed out waiting for the source sync/deploy lock"
cd "$REPO_DIR"
[[ "$(git branch --show-current)" == main ]] || fail "Production checkout must remain on main"
[[ -z "$(git status --porcelain)" ]] || fail "Production checkout is dirty"
systemctl is-active --quiet "$SERVICE" || fail "$SERVICE is not currently active; refusing an unverified deployment"
working_dir="$(systemctl show "$SERVICE" -p WorkingDirectory --value)"
exec_start="$(systemctl show "$SERVICE" -p ExecStart --value)"
[[ "$working_dir" == "$REPO_DIR/backend" ]] || fail "Unexpected service WorkingDirectory: $working_dir"
venv=""
for candidate in "$working_dir/venv" "$working_dir/.venv" "$REPO_DIR/backend/venv" "$REPO_DIR/backend/.venv" "$REPO_DIR/venv" "$REPO_DIR/.venv"; do
  if [[ -x "$candidate/bin/python" ]]; then venv="$candidate"; break; fi
done
[[ -n "$venv" ]] || fail "No existing application virtualenv found under backend/venv or supported .venv locations"
[[ "$exec_start" == *"$venv/bin/"* ]] || fail "Service ExecStart does not use detected virtualenv; refusing to switch runtime"
old_sha="$(git rev-parse --verify -q refs/deploy/last-good || git rev-parse HEAD)"
rollback_needed=0
rollback(){
  rc=$?
  if (( rollback_needed )); then
    log "Deployment failed; restoring $old_sha"
    git reset --hard "$old_sha" || log "CRITICAL: source rollback failed"
    "$venv/bin/python" -m pip install --disable-pip-version-check -r backend/requirements.txt || log "WARNING: previous dependencies could not be restored"
    sudo systemctl restart "$SERVICE" || log "CRITICAL: previous service restart failed"
    sleep 5
    curl --fail --silent --show-error --max-time 15 "$HEALTH_URL" >/dev/null || log "CRITICAL: rollback health check failed"
  fi
  exit "$rc"
}
trap rollback EXIT
git fetch --quiet origin main
git cat-file -e "$TARGET_SHA^{commit}" || fail "Target commit is not available locally after fetch"
git merge-base --is-ancestor "$old_sha" "$TARGET_SHA" || fail "Target is not a fast-forward from current production"
git merge --ff-only "$TARGET_SHA"
rollback_needed=1
"$venv/bin/python" -m pip install --disable-pip-version-check -r backend/requirements.txt
PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/superbajaar-pycache-${TARGET_SHA}" "$venv/bin/python" -m compileall -q backend/app
sudo systemctl restart "$SERVICE"
for attempt in $(seq 1 18); do
  if curl --fail --silent --show-error --max-time 10 "$HEALTH_URL" >/dev/null; then break; fi
  [[ "$attempt" -lt 18 ]] || fail "Health endpoint did not become healthy"
  sleep 5
done
hr_code="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 15 "$HR_ROUTE" || true)"
case "$hr_code" in 2??|401|403) ;; *) fail "HR route check failed with HTTP $hr_code" ;; esac
rollback_needed=0
git update-ref refs/deploy/last-good "$(git rev-parse HEAD)"
trap - EXIT
log "Deployment verified: $(git rev-parse HEAD); health=OK; HR route HTTP $hr_code"
