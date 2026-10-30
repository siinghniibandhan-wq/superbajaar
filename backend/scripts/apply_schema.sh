#!/usr/bin/env bash
# Super Bajaar database change runner (version 2).
# Owner: Claude by default; the owner may explicitly authorize a scoped implementation by another agent.
#
# Usage: apply_schema.sh <schema_dir> [--dry-run | --status | --retry]
#   (no option)  apply every new schema file, safely
#   --dry-run    show what would be applied, change nothing
#   --status     show the state of every file (applied / pending / failed / changed)
#   --retry      also retry files that failed before with the same content
#
# What it guarantees
#   1. A backup is taken (and checked) before any change. No backup = no change.
#   2. Every file runs in its own transaction. A failed file changes nothing.
#   3. Every file is recorded in schema_migrations with a checksum.
#   4. A failure is never silent: it is logged, stored in schema_migration_failures,
#      and sent to SB_ALERT_CMD if that is set. A failed file is not retried (and not
#      re-alerted) until its content changes, so a 2-minute poller does not spam.
#   5. An applied file that was edited later is reported, never re-applied.
#   6. One failed file does not block independent later files.
#   7. The release decides what it needs: files listed in schema_required.txt.
#
# Exit codes (the deploy should continue only on 0 or 11)
#   0   everything applied, nothing wrong
#   10  some file failed/changed and no schema_required.txt exists (strict: do not deploy)
#   11  some file failed/changed but every REQUIRED file is applied (deploy may continue)
#   20  a REQUIRED file is not applied (do not deploy, keep the old release)
#   30  backup failed, nothing was applied
#   50  setup problem (cannot connect, bad file name, unexpected ledger, ...)
#   60  another run is in progress
set -uo pipefail

DIR="${1:?usage: apply_schema.sh <schema_dir> [--dry-run|--status|--retry]}"
MODE="apply"; RETRY=0
case "${2:-}" in
  "") ;; --dry-run) MODE="dry" ;; --status) MODE="status" ;; --retry) RETRY=1 ;;
  *) echo "unknown option $2" >&2; exit 50 ;;
esac

DB="${SB_DB:-sb_app}"                                  # production database name (README)
PSQL="${SB_PSQL:-sudo -n -u postgres psql}"
PGDUMP="${SB_PGDUMP:-sudo -n -u postgres pg_dump}"
PGRESTORE="${SB_PGRESTORE:-pg_restore}"
BK="${SB_BACKUP_DIR:-/home/ec2-user/schema-backups}"
LOG="${SB_LOG:-/home/ec2-user/deploy/schema.log}"
REQ="${SB_REQUIRED_FILE:-$(dirname "$DIR")/schema_required.txt}"
HEALTH="${SB_HEALTH_URL-http://127.0.0.1:8001/api/health}"   # set empty to skip
LOCK="${SB_LOCK_FILE:-/tmp/sb_schema.lock}"
KEEP_DAYS="${SB_KEEP_DAYS:-14}"; KEEP_MIN="${SB_KEEP_MIN:-3}"
ALERT="${SB_ALERT_CMD:-}"                              # optional: command taking "subject" "body"
ON_FAILURE="${SB_ON_FAILURE:-continue}"                # continue | stop

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
log(){ echo "$(date -u +%FT%TZ) schema[$DB]: $*" | tee -a "$LOG" 2>/dev/null || echo "schema[$DB]: $*"; }
alert(){ log "ALERT: $1 | $2"; if [ -n "$ALERT" ]; then $ALERT "$1" "$2" >/dev/null 2>&1 || log "alert command failed"; fi; }
pg(){ $PSQL -X -q -At -v ON_ERROR_STOP=1 -d "$DB" "$@"; }
die(){ log "ERROR: $2"; exit "$1"; }

[ -d "$DIR" ] || die 50 "schema folder $DIR not found"
exec 9>"$LOCK" 2>/dev/null && { flock -n 9 || die 60 "another run is in progress"; }
pg -c "select 1" >/dev/null 2>&1 || die 50 "cannot connect to database $DB (check the name; README says sb_app)"

# ---- read the files in the folder -------------------------------------------------
FILES=(); declare -A FSUM
for f in $(ls "$DIR"/*.sql 2>/dev/null | sort); do
  n=$(basename "$f")
  [[ $n =~ ^[0-9]{3}_[a-z0-9_]+\.sql$ ]] || die 50 "unexpected file name $n (use NNN_name.sql, lowercase)"
  FILES+=("$n"); FSUM[$n]=$(sha256sum "$f" | cut -d' ' -f1)
done
[ ${#FILES[@]} -gt 0 ] || die 50 "no .sql files in $DIR"

# ---- read the ledger -------------------------------------------------------------
HAVE_LEDGER=$(pg -c "select to_regclass('public.schema_migrations') is not null")
declare -A LED
user_object_count(){
  pg -c "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND left(n.nspname,3)<>'pg_' AND c.relkind IN ('r','p','v','m','S','f') AND NOT (n.nspname='public' AND c.relname IN ('schema_migrations','schema_migration_failures','schema_migration_failures_id_seq'))) + (SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','public') AND left(nspname,3)<>'pg_')"
}

if [ "$HAVE_LEDGER" = t ]; then
  cols=$(pg -c "select count(*) from information_schema.columns where table_schema='public' and table_name='schema_migrations' and column_name in ('filename','sha256')")
  [ "$cols" = 2 ] || die 50 "schema_migrations has an unexpected shape; do not continue, ask Claude"
  while IFS='|' read -r fn sm; do [ -n "$fn" ] && LED[$fn]=$sm; done < <(pg -c "select filename, sha256 from schema_migrations")
else
  objects=$(user_object_count) || die 50 "cannot inspect database objects; refusing to guess"
  [ "$objects" = 0 ] || die 50 "database has user objects but no schema_migrations ledger; refusing to guess, ask Claude"
fi

BASELINE="000_baseline_schema.sql"
if [ "$HAVE_LEDGER" = t ] && [ -n "${FSUM[$BASELINE]:-}" ] && [ -z "${LED[$BASELINE]:-}" ]; then
  objects=$(user_object_count) || die 50 "cannot inspect database objects before baseline; refusing to continue"
  [ "$objects" = 0 ] || die 50 "baseline $BASELINE is not recorded in schema_migrations but the database already contains $objects user objects; refusing to apply a draft baseline"
fi
declare -A KF   # known failures: "file|sha" -> 1
if [ "$(pg -c "select to_regclass('public.schema_migration_failures') is not null")" = t ]; then
  while IFS='|' read -r fn sm; do [ -n "$fn" ] && KF["$fn|$sm"]=1; done < <(pg -c "select distinct filename, sha256 from schema_migration_failures")
fi

# ---- classify each file ----------------------------------------------------------
PENDING=(); CHANGED=(); KNOWN_FAILED=()
for n in "${FILES[@]}"; do
  sm=${FSUM[$n]}
  if [ -n "${LED[$n]:-}" ]; then
    [ "${LED[$n]}" = "$sm" ] || { if [ -n "${KF["$n|$sm"]:-}" ] && [ $RETRY = 0 ]; then KNOWN_FAILED+=("$n"); else CHANGED+=("$n"); fi; }
  else
    if [ -n "${KF["$n|$sm"]:-}" ] && [ $RETRY = 0 ]; then KNOWN_FAILED+=("$n"); else PENDING+=("$n"); fi
  fi
done

# ---- required files for this release ---------------------------------------------
REQUIRED=(); HAVE_REQ=0
if [ -f "$REQ" ]; then
  HAVE_REQ=1
  while read -r line; do
    line="${line%%#*}"; line="$(echo "$line" | xargs)"; [ -z "$line" ] && continue
    [ -n "${FSUM[$line]:-}" ] || die 50 "schema_required.txt lists $line but that file is not in $DIR"
    REQUIRED+=("$line")
  done < "$REQ"
fi
missing_required(){ local m=(); for r in "${REQUIRED[@]:-}"; do [ -z "$r" ] && continue; [ "${LED[$r]:-}" = "${FSUM[$r]}" ] || m+=("$r"); done; echo "${m[*]:-}"; }

finish(){  # decides the exit code from the current state
  local problems=$(( ${#FAILED_NOW[@]} + ${#CHANGED[@]} + ${#KNOWN_FAILED[@]} + ${#PENDING_LEFT[@]} ))
  local miss; miss=$(missing_required)
  if [ $HAVE_REQ = 1 ] && [ -n "$miss" ]; then
    alert "Super Bajaar: deploy blocked" "The new release needs database file(s) that are not applied: $miss. The old release stays live."
    log "RESULT code=20 missing_required=$miss"; exit 20
  fi
  if [ $problems -gt 0 ]; then
    if [ $HAVE_REQ = 1 ]; then log "RESULT code=11 problems=$problems (all required files applied)"; exit 11; fi
    log "RESULT code=10 problems=$problems (no schema_required.txt, strict)"; exit 10
  fi
  log "RESULT code=0 all files applied"; exit 0
}
FAILED_NOW=(); PENDING_LEFT=()

# ---- status / dry run ------------------------------------------------------------
if [ "$MODE" = status ] || [ "$MODE" = dry ]; then
  echo "database: $DB   files: ${#FILES[@]}   required list: $([ $HAVE_REQ = 1 ] && echo "$REQ" || echo none)"
  for n in "${FILES[@]}"; do
    st=APPLIED
    [[ " ${PENDING[*]:-} " == *" $n "* ]] && st="PENDING (would be applied)"
    [[ " ${CHANGED[*]:-} " == *" $n "* ]] && st="CHANGED after it was applied (needs a person)"
    [[ " ${KNOWN_FAILED[*]:-} " == *" $n "* ]] && st="FAILED earlier (not retried until the file changes)"
    req=""; [[ " ${REQUIRED[*]:-} " == *" $n "* ]] && req=" [required]"
    echo "  $n: $st$req"
  done
  for k in "${!LED[@]}"; do [ -n "${FSUM[$k]:-}" ] || echo "  note: ledger has $k but the file is not in the folder (old record)"; done
  if [ "$HAVE_LEDGER" = t ] && [ "$(pg -c "select to_regclass('public.schema_migration_failures') is not null")" = t ]; then
    pg -c "select '  last error for '||filename||': '||left(regexp_replace(error,E'[\\r\\n|]+',' ','g'),200) from (select distinct on (filename) filename,error from schema_migration_failures order by filename, failed_at desc) t"
  fi
  PENDING_LEFT=("${PENDING[@]:-}"); [ -z "${PENDING[*]:-}" ] && PENDING_LEFT=()
  p=$(( ${#CHANGED[@]} + ${#KNOWN_FAILED[@]} )); miss=$(missing_required)
  if [ "$MODE" = status ] && { [ $p -gt 0 ] || [ -n "${PENDING[*]:-}" ] || { [ $HAVE_REQ = 1 ] && [ -n "$miss" ]; }; }; then
    alert "Super Bajaar: database files need attention" "Run: apply_schema.sh $DIR --status on the server. Failed/changed: ${KNOWN_FAILED[*]:-} ${CHANGED[*]:-} Pending: ${PENDING[*]:-}"
    exit 10
  fi
  exit 0
fi

# ---- nothing to apply ------------------------------------------------------------
if [ ${#PENDING[@]} -eq 0 ]; then
  [ ${#CHANGED[@]} -gt 0 ] && for n in "${CHANGED[@]}"; do
    alert "Super Bajaar: a database file was edited after it was applied" "$n changed after it was applied. It was NOT re-applied. Ask Claude for a new numbered file."
    printf '%s\n' "INSERT INTO schema_migration_failures(filename,sha256,error) VALUES (:'fn',:'sm','changed after it was applied; not re-applied');" | pg -v fn="$n" -v sm="${FSUM[$n]}" >/dev/null 2>&1 || true
  done
  log "no new files to apply (${#FILES[@]} files known)"; finish
fi
log "pending: ${PENDING[*]}"

# ---- backup first ----------------------------------------------------------------
mkdir -p "$BK" 2>/dev/null || { alert "Super Bajaar: backup failed" "Cannot create $BK. Nothing was changed."; die 30 "cannot create backup folder"; }
F="$BK/$DB-pre-migration-$(date -u +%Y%m%dT%H%M%SZ).dump"
if $PGDUMP -Fc "$DB" > "$F" 2>>"$LOG" && [ -s "$F" ] && $PGRESTORE --list "$F" >/dev/null 2>&1; then
  chmod 600 "$F"; log "backup ok: $F"
else
  rm -f "$F"; alert "Super Bajaar: backup FAILED" "No database change was made because the backup failed."; die 30 "backup failed; nothing applied"
fi
n_keep=0; for old in $(ls -1t "$BK"/*.dump 2>/dev/null); do
  n_keep=$((n_keep+1)); [ $n_keep -le "$KEEP_MIN" ] && continue
  [ -n "$(find "$old" -mtime +"$KEEP_DAYS" 2>/dev/null)" ] && rm -f "$old"
done

# ---- apply ------------------------------------------------------------------------
pg -c "CREATE TABLE IF NOT EXISTS schema_migrations(filename TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), baseline BOOLEAN NOT NULL DEFAULT false)" || die 50 "cannot create schema_migrations"
pg -c "CREATE TABLE IF NOT EXISTS schema_migration_failures(id BIGSERIAL PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL, failed_at TIMESTAMPTZ NOT NULL DEFAULT now(), error TEXT NOT NULL)" || die 50 "cannot create schema_migration_failures"

for n in "${PENDING[@]}"; do
  f="$DIR/$n"; sm=${FSUM[$n]}
  log "applying $n"
  # Permissions must be declared explicitly in the migration itself. Never grant
  # blanket access to every public table/sequence as a side effect of one migration.
  out=$({ echo "BEGIN;"; cat "$f"; echo
          echo "INSERT INTO schema_migrations(filename,sha256) VALUES ('$n','$sm');"
          echo "COMMIT;"; } | pg 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    log "applied $n"; LED[$n]=$sm
  else
    err=$(printf '%s\n' "$out" | grep -m1 -E 'ERROR|FATAL' || true); [ -z "$err" ] && err=$(printf '%s' "$out" | head -c 300)
    err="${err:0:400}"
    printf '%s\n' "INSERT INTO schema_migration_failures(filename,sha256,error) VALUES (:'fn',:'sm',:'er');" | pg -v fn="$n" -v sm="$sm" -v er="$err" >/dev/null 2>&1 || log "could not record failure of $n"
    FAILED_NOW+=("$n"); PENDING_LEFT+=("$n")
    alert "Super Bajaar: database change FAILED ($n)" "$n failed and was rolled back, nothing from it was changed. Reason: $err. Backup: $F. Other independent files are still applied."
    [ "$ON_FAILURE" = stop ] && { log "stopping because SB_ON_FAILURE=stop"; break; }
  fi
done

if [ -n "$HEALTH" ]; then
  code=$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "$HEALTH" 2>/dev/null || echo 000)
  [ "$code" = 200 ] && log "health check ok ($HEALTH)" || alert "Super Bajaar: health check not OK after database change" "$HEALTH returned HTTP $code. Backup: $F"
fi
finish