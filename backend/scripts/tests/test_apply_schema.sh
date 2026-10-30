#!/usr/bin/env bash
# Tests for apply_schema.sh against a REAL Postgres. Never run against production.
# Needs: SB_PSQL, SB_PGDUMP (and psql/pg_dump/pg_restore on PATH), pointing at a throw-away server.
# Usage: SB_PSQL="psql -h localhost -U postgres" SB_PGDUMP="pg_dump -h localhost -U postgres" \
#        test_apply_schema.sh <real_schema_dir> <real_required_file>
set -uo pipefail
REAL_DIR="${1:?real schema dir}"; REAL_REQ="${2:?real schema_required.txt}"
RUNNER="$(cd "$(dirname "$0")/.." && pwd)/apply_schema.sh"
: "${SB_PSQL:?}" "${SB_PGDUMP:?}"
case "$SB_PSQL" in *sudo*|*sb_app*) echo "refusing: looks like production"; exit 99;; esac
export SB_PSQL SB_PGDUMP
T=$(mktemp -d); pass=0; fail=0
ok(){ pass=$((pass+1)); echo "  PASS: $1"; }
bad(){ fail=$((fail+1)); echo "  FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
newdb(){ DBN="t_$$_$RANDOM"; $SB_PSQL -X -q -d postgres -c "CREATE DATABASE $DBN" >/dev/null; export SB_DB="$DBN"; export SB_BACKUP_DIR="$T/bk_$DBN" SB_LOG="$T/log_$DBN" SB_LOCK_FILE="$T/lock_$DBN" SB_ALERT_CMD="$T/alert.sh" SB_HEALTH_URL=""; : > "$T/alerts"; }
q(){ $SB_PSQL -X -q -At -d "$SB_DB" -c "$1"; }
run(){ "$RUNNER" "$@" >"$T/out" 2>&1; echo $?; }
printf '#!/usr/bin/env bash\necho "$1 :: $2" >> %s/alerts\n' "$T" > "$T/alert.sh"; chmod +x "$T/alert.sh"
dumps(){ ls "$SB_BACKUP_DIR"/*.dump 2>/dev/null | wc -l | tr -d ' '; }

echo "T1 fresh database, real schema files"
newdb; mkdir "$T/s1"; cp "$REAL_DIR"/*.sql "$T/s1/"; cp "$REAL_REQ" "$T/req1.txt"; export SB_REQUIRED_FILE="$T/req1.txt"
check "exit 0" "$(run "$T/s1")" 0
check "all files recorded" "$(q 'select count(*) from schema_migrations')" "$(ls "$T/s1"/*.sql | wc -l | tr -d ' ')"
check "one backup taken" "$(dumps)" 1
check "phone rule exists" "$(q "select count(*) from pg_indexes where indexname='customer_accounts_phone_digits_uidx'")" 1

echo "T2 second run changes nothing"
check "exit 0" "$(run "$T/s1")" 0
check "no new backup" "$(dumps)" 1

echo "T3 one bad file, one good file after it"
cp "$T/s1"/*.sql "$T/" 2>/dev/null; mkdir "$T/s3"; cp "$T/s1"/*.sql "$T/s3/"
printf "CREATE TABLE t_half(id int);\nSELEC 1;\n" > "$T/s3/013_bad_syntax.sql"
printf "CREATE TABLE IF NOT EXISTS t_good(id int);\n" > "$T/s3/014_good.sql"
printf '%s\n' "000_baseline_schema.sql" "014_good.sql" > "$T/req3.txt"; export SB_REQUIRED_FILE="$T/req3.txt"
check "exit 11 (failure, but required ok)" "$(run "$T/s3")" 11
check "good file applied" "$(q "select count(*) from schema_migrations where filename='014_good.sql'")" 1
check "bad file NOT in ledger" "$(q "select count(*) from schema_migrations where filename='013_bad_syntax.sql'")" 0
check "bad file rolled back (no half table)" "$(q "select to_regclass('public.t_half') is null")" t
check "failure recorded" "$(q "select count(*) from schema_migration_failures")" 1
check "alert sent" "$(grep -c 'FAILED (013_bad_syntax.sql)' "$T/alerts")" 1

echo "T4 rerun: no retry, no new backup, no alert spam"
b=$(dumps); check "exit 11" "$(run "$T/s3")" 11
check "no new backup" "$(dumps)" "$b"
check "no new failure row" "$(q "select count(*) from schema_migration_failures")" 1
check "still one alert" "$(wc -l < "$T/alerts" | tr -d ' ')" 1

echo "T5 release that REQUIRES the failed file is blocked"
printf '%s\n' "013_bad_syntax.sql" > "$T/req5.txt"; check "exit 20" "$(SB_REQUIRED_FILE="$T/req5.txt" run "$T/s3")" 20

echo "T6 no required list means strict"
check "exit 10" "$(SB_REQUIRED_FILE="$T/none.txt" run "$T/s3")" 10

echo "T7 fixing the file retries it automatically"
printf "CREATE TABLE IF NOT EXISTS t_fixed(id int);\n" > "$T/s3/013_bad_syntax.sql"
check "exit 0" "$(run "$T/s3")" 0
check "fixed file applied" "$(q "select count(*) from schema_migrations where filename='013_bad_syntax.sql'")" 1

echo "T8 editing an applied file is reported, not re-applied"
printf "CREATE TABLE IF NOT EXISTS t_good(id int, extra int);\n" > "$T/s3/014_good.sql"
: > "$T/alerts"; r=$(run "$T/s3"); check "exit 20 (a required file no longer matches what was applied)" "$r" 20
check "not re-applied" "$(q "select count(*) from information_schema.columns where table_name='t_good' and column_name='extra'")" 0
check "alert about edit" "$(grep -c 'edited after it was applied' "$T/alerts")" 1
run "$T/s3" >/dev/null; check "no repeat alert" "$(grep -c 'edited after it was applied' "$T/alerts")" 1

echo "T9 backup failure stops everything"
printf "CREATE TABLE IF NOT EXISTS t_after_backup_fail(id int);\n" > "$T/s3/015_next.sql"
check "exit 30" "$(SB_PGDUMP=false run "$T/s3")" 30
check "nothing applied" "$(q "select count(*) from schema_migrations where filename='015_next.sql'")" 0

export SB_REQUIRED_FILE="$T/none.txt"   # no required list from here on
echo "T10 bad file name"
mkdir "$T/s10"; echo "select 1;" > "$T/s10/Bad-Name.sql"; newdb; check "exit 50" "$(run "$T/s10")" 50
grep -q "unexpected file name" "$T/out" && ok "reason is the file name" || bad "wrong reason: $(head -c 200 "$T/out")"

echo "T11 database with tables but no ledger is refused"
newdb; q "create table products(id int)" ; mkdir -p "$T/s11"; echo "select 1;" > "$T/s11/001_x.sql"; check "exit 50" "$(run "$T/s11")" 50
grep -q "no schema_migrations ledger" "$T/out" && ok "reason is the missing ledger" || bad "wrong reason: $(head -c 200 "$T/out")"

echo "T12 dry run and status change nothing"
newdb; mkdir -p "$T/s12"; echo "create table t12(id int);" > "$T/s12/001_a.sql"; check "dry run exit 0" "$(run "$T/s12" --dry-run)" 0
check "dry run applied nothing" "$(q "select to_regclass('public.t12') is null")" t
check "apply exit 0" "$(run "$T/s12")" 0
check "status exit 0" "$(run "$T/s12" --status)" 0
grep -q "001_a.sql: APPLIED" "$T/out" && ok "status shows APPLIED" || bad "status output"

echo "T13 two runs at once"
newdb; ( exec 8>"$SB_LOCK_FILE"; flock 8; sleep 4 ) & sleep 1; check "exit 60" "$(run "$T/s12")" 60; wait

echo "T14 error text with quotes is stored safely"
newdb; mkdir -p "$T/s14"; printf "SELECT * FROM \"no'such\";\n" > "$T/s14/001_q.sql"; check "exit 10" "$(run "$T/s14")" 10
check "failure stored" "$(q "select count(*) from schema_migration_failures")" 1

echo "T15 migration grants only its explicitly declared least-privilege permissions"
newdb
$SB_PSQL -X -q -d postgres -c "DO \$\$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sb_app_user_t') THEN CREATE ROLE sb_app_user_t LOGIN; END IF; END\$\$;" >/dev/null
$SB_PSQL -X -q -d "$SB_DB" -c "CREATE TABLE existing_sensitive(id integer); CREATE TABLE schema_migrations(filename text primary key, sha256 text not null, applied_at timestamptz not null default now(), baseline boolean not null default false);" >/dev/null
mkdir -p "$T/s15"
cat > "$T/s15/001_g.sql" <<'SQL'
CREATE TABLE t15(id bigserial primary key, value text);
GRANT SELECT, INSERT ON t15 TO sb_app_user_t;
GRANT USAGE, SELECT ON SEQUENCE t15_id_seq TO sb_app_user_t;
SQL
check "exit 0" "$(run "$T/s15")" 0
check "explicit SELECT and INSERT grants work" "$(q "select has_table_privilege('sb_app_user_t','t15','SELECT,INSERT')")" t
check "UPDATE and DELETE were not granted" "$(q "select has_table_privilege('sb_app_user_t','t15','UPDATE,DELETE')")" f
check "sequence access is explicitly granted" "$(q "select has_sequence_privilege('sb_app_user_t','t15_id_seq','USAGE,SELECT')")" t
check "unrelated existing table receives no automatic grant" "$(q "select has_table_privilege('sb_app_user_t','existing_sensitive','SELECT')")" f

echo "T16 pending baseline is blocked on a populated database"
newdb
$SB_PSQL -X -q -d "$SB_DB" -c "CREATE TABLE schema_migrations(filename text primary key, sha256 text not null, applied_at timestamptz not null default now(), baseline boolean not null default false); CREATE TABLE existing_products(id bigint primary key);" >/dev/null
mkdir -p "$T/s16"; cp "$REAL_DIR/000_baseline_schema.sql" "$T/s16/"
printf '%s\n' "000_baseline_schema.sql" > "$T/req16.txt"
export SB_REQUIRED_FILE="$T/req16.txt"
check "exit 50 (baseline blocked on populated DB)" "$(run "$T/s16")" 50
check "no backup taken before baseline refusal" "$(dumps)" 0
check "baseline did not create categories" "$(q "select to_regclass('public.categories') is null")" t
grep -q "refusing to apply a draft baseline" "$T/out" && ok "baseline refusal explains why" || bad "baseline refusal message missing"

echo; echo "RESULT: $pass passed, $fail failed"; rm -rf "$T"; [ $fail -eq 0 ]