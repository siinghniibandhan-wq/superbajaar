#!/usr/bin/env bash
set -Eeuo pipefail
# Safe, pull-only synchronisation of the production checkout with origin/main.
# No build, migration, service restart, reset, clean, or force operation is run.
REPO_DIR="${SB_SYNC_REPO_DIR:-/opt/superbajaar/source}"
REMOTE="${SB_SYNC_REMOTE:-origin}"
BRANCH="${SB_SYNC_BRANCH:-main}"
LOG_FILE="${SB_SYNC_LOG_FILE:-/var/log/superbajaar-github-sync.log}"
# Shared with deploy_backend.sh: serialize source checkout updates and deployments.
LOCK_FILE="${SB_SYNC_LOCK_FILE:-/run/lock/superbajaar-source.lock}"
log() {
  local message="$*"
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$message" | tee -a "$LOG_FILE" 2>/dev/null || printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$message" >&2
}
fail() { log "ERROR: $*"; exit 1; }
command -v git >/dev/null 2>&1 || fail "git is not installed"
command -v flock >/dev/null 2>&1 || fail "flock is not installed"
[[ -d "$REPO_DIR/.git" ]] || fail "Git checkout not found at $REPO_DIR"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -n 9 || { log "Another synchronisation is already running; skipping"; exit 0; }
cd "$REPO_DIR"
current_branch="$(git branch --show-current)"
[[ "$current_branch" == "$BRANCH" ]] || fail "Checkout is on '$current_branch', expected '$BRANCH'; refusing to switch branches"
if [[ -n "$(git status --porcelain)" ]]; then
  fail "Working tree is not clean; refusing to overwrite server-local changes"
fi
git remote get-url "$REMOTE" >/dev/null 2>&1 || fail "Remote '$REMOTE' is not configured"
log "Checking $REMOTE/$BRANCH for updates"
git fetch --quiet --prune "$REMOTE" "$BRANCH" || fail "git fetch failed"
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "$REMOTE/$BRANCH")"
if [[ "$local_sha" == "$remote_sha" ]]; then
  log "Already current at $local_sha"
  exit 0
fi
if ! git merge-base --is-ancestor HEAD "$REMOTE/$BRANCH"; then
  fail "Remote branch is not a fast-forward from local HEAD; manual review required"
fi
# Recheck immediately before merge to avoid applying over an intervening local edit.
if [[ -n "$(git status --porcelain)" ]]; then
  fail "Working tree became dirty during fetch; refusing to update"
fi
git merge --ff-only --no-edit "$REMOTE/$BRANCH" >/dev/null || fail "Fast-forward update failed"
new_sha="$(git rev-parse HEAD)"
log "Updated main from $local_sha to $new_sha"
log "Code synchronised only; no migrations, builds, or service restarts were run"
