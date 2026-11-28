#!/usr/bin/env bash
set -Eeuo pipefail
: "${SB_STAGING_DATABASE_URL:?Set SB_STAGING_DATABASE_URL to the isolated staging database}"
command -v psql >/dev/null || { echo "psql is required" >&2; exit 1; }
db_name="$(psql "${SB_STAGING_DATABASE_URL}" -Atqc 'select current_database()')"
case "${db_name,,}" in *stage*|*staging*|*test*) ;; *) echo "Refusing HR migration run against non-staging database: $db_name" >&2; exit 1;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
schema="$repo_root/backend/schema"
migrations=(
  071_hr_enterprise_workflows.sql
  072_hr_enterprise_integrity.sql
  073_recruitment_integrity.sql
  074_hr_enterprise_notifications.sql
  075_hr_employee_job_grades.sql
  076_hr_exit_and_loan_ledger.sql
  077_hr_travel_advance_disbursements.sql
  078_hr_travel_payout_beneficiaries.sql
)
for migration in "${migrations[@]}"; do
  file="$schema/$migration"
  [[ -f "$file" ]] || { echo "Missing migration: $file" >&2; exit 1; }
  echo "Applying $migration to staging database $db_name"
  psql "${SB_STAGING_DATABASE_URL}" -v ON_ERROR_STOP=1 --single-transaction -f "$file"
done
echo "HR enterprise migrations completed on staging database $db_name"
