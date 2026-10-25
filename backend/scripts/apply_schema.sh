#!/bin/bash
# Version-tracked, idempotent schema migrations.
# Usage: apply_schema.sh <schema_dir> [--dry-run]
set -uo pipefail
DIR="${1:?usage: apply_schema.sh <schema_dir> [--dry-run]}"; DRY="${2:-}"
DB=superbajaar; BK=/home/ec2-user/schema-backups; LOG=/home/ec2-user/deploy/schema.log
ENVF=/home/ec2-user/superbajaar/backend/.env; API=http://127.0.0.1:8000/api/products
BASELINE="001_product_inventory_foundation.sql 002_suppliers_purchasing.sql 003_serviceability.sql"
log(){ echo "$(date -u +%FT%TZ) schema: $*" | tee -a "$LOG"; }
die(){ log "ERROR: $*"; exit 1; }
pg(){ sudo -n -u postgres psql -X -q -At -v ON_ERROR_STOP=1 -d "$DB" "$@"; }

pg -c "select 1" >/dev/null || die "cannot connect to database"
HAVE=$(pg -c "select to_regclass('public.schema_migrations') is not null")
BASE_NEEDED=0
if [ "$HAVE" != t ] && [ "$(pg -c "select to_regclass('public.products') is not null")" = t ]; then BASE_NEEDED=1; fi

PENDING=()
for f in $(ls "$DIR"/[0-9][0-9][0-9]_*.sql | sort); do
  n=$(basename "$f")
  [[ $n =~ ^[0-9]{3}_[a-z0-9_]+\.sql$ ]] || die "unexpected filename $n"
  sum=$(sha256sum "$f" | cut -d' ' -f1)
  if [ $BASE_NEEDED = 1 ] && [[ " $BASELINE " == *" $n "* ]]; then continue; fi
  old=""; [ "$HAVE" = t ] && old=$(pg -c "select sha256 from schema_migrations where filename='$n'")
  if [ -n "$old" ]; then
    [ "$old" = "$sum" ] || die "$n changed after it was applied; add a new numbered file instead"
    continue
  fi
  PENDING+=("$n")
done

if [ ${#PENDING[@]} -eq 0 ] && [ $BASE_NEEDED = 0 ]; then log "schema up to date"; exit 0; fi
log "pending: ${PENDING[*]:-none} baseline_needed=$BASE_NEEDED"
[ "$DRY" = --dry-run ] && { log "dry run, nothing changed"; exit 0; }

ROLE=$(bash -c "set -a; . $ENVF; set +a; U=\"${DATABASE_URL#*://}\"; echo \"${U%%[:@]*}\"")
[[ $ROLE =~ ^[a-z_][a-z0-9_]*$ ]] || die "cannot determine app database role"

mkdir -p "$BK"; F="$BK/superbajaar-pre-migration-$(date -u +%Y%m%dT%H%M%SZ).dump"
sudo -n -u postgres pg_dump -Fc "$DB" > "$F" && pg_restore --list "$F" >/dev/null && chmod 600 "$F" \
  || { rm -f "$F"; die "backup failed; nothing applied"; }
log "backup ok: $F"
find "$BK" -name '*.dump' -mtime +14 -delete

pg -c "CREATE TABLE IF NOT EXISTS schema_migrations(filename TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), baseline BOOLEAN NOT NULL DEFAULT false)" || die "cannot create schema_migrations"
if [ $BASE_NEEDED = 1 ]; then
  for n in $BASELINE; do
    [ -f "$DIR/$n" ] || { log "baseline $n not in release, skipped"; continue; }
    sum=$(sha256sum "$DIR/$n" | cut -d' ' -f1)
    pg -c "INSERT INTO schema_migrations(filename,sha256,baseline) VALUES ('$n','$sum',true) ON CONFLICT DO NOTHING" || die "baseline $n"
  done
  log "baselined 001-003 (recorded, not executed)"
fi

for n in "${PENDING[@]}"; do
  sum=$(sha256sum "$DIR/$n" | cut -d' ' -f1)
  log "applying $n"
  { echo "BEGIN;"; cat "$DIR/$n"; echo
    echo "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"$ROLE\";"
    echo "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO \"$ROLE\";"
    echo "INSERT INTO schema_migrations(filename,sha256) VALUES ('$n','$sum');"; echo "COMMIT;"; } \
    | pg >>"$LOG" 2>&1 || die "$n failed and was rolled back (earlier files stay applied). Backup: $F"
  log "applied $n"
done

code=$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "$API" 2>/dev/null || echo "000")
[ "$code" = 200 ] || die "schema applied but $API returned HTTP $code. Backup: $F"
log "schema OK (api HTTP 200)"
