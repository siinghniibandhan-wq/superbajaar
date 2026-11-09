# Database Change Request: HR statutory history guards (029)

## Scope
Add database-level immutability protections to hr_statutory_audit_events and hr_payroll_statutory_snapshots.

## Compatibility review
- Existing backend/app/api/hr.py writes audit events with INSERT only.
- Payroll recalculation locks the run row with SELECT FOR UPDATE, then deletes/rebuilds statutory snapshots only while the run is draft or calculated.
- The snapshot trigger takes the same parent-row lock before checking status, preventing a concurrent approval/recalculation race.
- The audit trigger permits only the existing FK-driven actor_user_id value-to-NULL transition when an application user is deleted.
- No API contract, table shape, existing row, grant, role, table owner, or application runtime code changes.
- No schema_required.txt entry is needed because application code does not depend on a new object.

## Database Change Request
- Tables: hr_statutory_audit_events, hr_payroll_statutory_snapshots, and a read-only status check against hr_payroll_runs.
- Existing data: preserved; the migration does not update or delete existing rows.
- Role/identity rules: unchanged.
- Production preflight: owner must verify the live ledger and backup readiness before any deployment.

## Test coverage
backend/tests/test_hr_statutory_history_guards.py exercises:
- audit UPDATE and DELETE rejection;
- actor-user FK SET NULL compatibility;
- snapshot UPDATE rejection;
- snapshot DELETE allowed for draft/calculated runs;
- snapshot DELETE rejected for approved/paid/void runs;
- fixture transaction rollback.

CI runs the complete schema twice on disposable PostgreSQL 15 and 16, then runs backend tests against that disposable database.

## Rollback
Do not edit migration 029 after merge/application. A separately approved migration 030 may remove only the two triggers and two guard functions. It must be tested and backed up independently.
