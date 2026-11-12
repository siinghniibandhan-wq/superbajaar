# Unified Identity System — production rollout runbook

**Purpose:** Controlled deployment and database migration of the merged Unified Identity System.  
**Code baseline:** PR #58 merge commit `f0182f083a4e34d3c07411b8433c9217b7c4024b`  
**Current state in this repository:** Code merged; production deployment and migration state are not verified.  
**Approval boundary:** This document is a runbook, not production authorization.

## 1. Scope and release components

Application changes are merged through PRs #54, #55, #57 and #58. The database release gate lists:

- `043_unified_identity_foundation.sql`
- `044_identity_loyalty_referral_links.sql`
- `045_identity_claim_cancellation_event.sql`

The backend and frontend deployments are separate release actions. Database migration is a third, separately controlled action. Do not infer that one action completed because another did.

## 2. Production facts and critical path

The repository's [Database Migrations](DATABASE_MIGRATIONS.md) runbook records the production database as self-managed PostgreSQL on the EC2 host, database `superbajaar`, application role `superbajaar_app`, port 5432 and host `127.0.0.1`. It records the source checkout at `/opt/superbajaar/source`.

The migration runner defaults to `sb_app` if `SB_DB` is not set. That default must never be used for a production operation. Use the explicit `SB_DB=superbajaar` environment in the documented production commands.

The documented systemd timer is **status-only**. Its effective service command must end with `--status`. It does not automatically apply migrations. Inspect merged unit configuration (including drop-ins) before relying on it.

Because infrastructure can change, re-verify these values on the host before an operation. This runbook does not claim a live EC2 inspection was performed.

## 3. Understand the GitHub production workflow triggers

The current `.github/workflows/deploy.yml` is configured for every push to `main` as well as manual dispatch. It first runs a full source verification job; after that succeeds, it can deploy the backend to EC2 through SSM and run the Amplify frontend verification/automatic-restore workflow. Its push trigger has no path filter, so a documentation-only push can start a production deployment. The backend deployment script does not apply database migrations; it fast-forwards the production checkout, installs backend requirements, compiles the backend, restarts the backend service and checks API/HR health. A push to `main` must therefore be treated as a potential production release until the workflow is explicitly cancelled or has completed and been inspected.

The separate `.github/workflows/production-database-migrations.yml` is path-filtered to changes under `backend/schema/**` or `backend/schema_required.txt`. Such a push starts production source verification and a read-only migration dry-run. Actual apply is not performed by a push: it requires `workflow_dispatch` with operation `apply`, the exact confirmation string `APPLY SUPERBAJAAR`, and approval through the protected GitHub environment `production-database`. Do not dispatch that apply workflow without separate explicit production approval.

**12 November 2026 documentation-push incident:** commit `dbe9a7949e72a961afda2a628eb24983c1b3d828` triggered deploy workflow run [43156606739](https://github.com/siinghniibandhan-wq/superbajaar/actions/runs/43156606739). It was cancelled while the verification job was still running and before the EC2 deployment and Amplify jobs started. The run's recorded final state was cancelled. This is recorded for transparency; it does not replace checking the current production release state.

## 4. Pre-deployment checks

1. Confirm `main` points to the approved release commit.
2. Confirm the intended backend deployment workflow, service target and frontend hosting workflow.
3. Confirm all required schema files 043–045 are present in the release checkout and listed in `backend/schema_required.txt`.
4. Review the complete diffs for migrations 043–045. Confirm they are additive and do not contain shell/systemd/deployment tooling.
5. Confirm the deployment workflow will not run an implicit migration apply outside the reviewed procedure.
6. Confirm no unrelated migration is unexpectedly pending or changed.
7. Confirm the exact database target from the live service configuration; never guess from a README or runner default.
8. Confirm there is a tested rollback/recovery plan for application artifacts and a database restore decision-maker.

## 5. Verify the schema timer is status-only

On the production EC2 host:

```bash
sudo systemctl cat superbajaar-schema.service
sudo systemctl cat superbajaar-schema.timer
sudo systemctl status superbajaar-schema.timer
sudo systemctl list-timers --all | grep superbajaar-schema
```

Inspect the effective `ExecStart` including drop-in overrides. It must invoke the runner with `--status`, not default apply mode. If it does not, stop and obtain an operations review before proceeding.

Inspect recent status output:

```bash
sudo journalctl -u superbajaar-schema.service --since "24 hours ago"
sudo tail -n 200 /var/log/superbajaar/schema.log
```

The systemd unit may treat runner exit code 10 as a successful oneshot execution. This is only a completed status check that found attention is needed; it is not proof all migrations are applied.

## 6. Preflight database status and dry-run

Use the documented host paths and explicit database/client/backup/log settings. Run only after confirming the host and target database:

```bash
sudo env SB_DB=superbajaar SB_PSQL=/usr/local/bin/sb-psql SB_BACKUP_DIR=/var/lib/superbajaar/backups SB_LOG=/var/log/superbajaar/schema.log \
  /bin/bash /opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema --status
```

Then preview pending files:

```bash
sudo env SB_DB=superbajaar SB_PSQL=/usr/local/bin/sb-psql SB_BACKUP_DIR=/var/lib/superbajaar/backups SB_LOG=/var/log/superbajaar/schema.log \
  /bin/bash /opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema --dry-run
```

Both commands connect to the configured database. Confirm `SB_DB` and the effective PostgreSQL client before running. Do not execute them against an unknown or guessed target.

Expected review: identify whether 043, 044 and 045 are pending, applied with matching checksums, failed, or changed after application. A changed applied migration is a stop condition; do not edit the ledger or force reapplication.

## 7. Backup gate and approval

Before apply:

- Confirm adequate disk space at `/var/lib/superbajaar/backups`.
- Confirm the configured `pg_dump` and `pg_restore` executables/permissions work.
- Confirm the runner can create a custom-format dump and validate it with `pg_restore --list`.
- Record the exact backup filename and UTC timestamp.
- Confirm a database-owner-approved recovery plan and decision-maker.
- Obtain explicit approval for this specific production database migration.

The runner itself creates and verifies a backup before applying pending files. If backup creation or verification fails, it exits with code 30 and does not apply SQL. Do not bypass this gate.

## 8. Controlled apply

Only after the preceding checks and separate explicit production approval, run:

```bash
sudo env SB_DB=superbajaar SB_PSQL=/usr/local/bin/sb-psql SB_BACKUP_DIR=/var/lib/superbajaar/backups SB_LOG=/var/log/superbajaar/schema.log \
  /bin/bash /opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema
```

No mode flag means apply mode. Never place this command in a timer or unattended recurring job. The runner uses a lock, one transaction per migration, and writes filenames/checksums to `schema_migrations`; failures are recorded in `schema_migration_failures`.

Stop on exit codes 20, 30, 50 or 60. Code 11 means some non-required issue remains although all required migrations are applied; inspect and document the issue before deciding whether the application release can proceed. Do not interpret code 0 alone as complete end-to-end validation.

## 9. Post-migration verification

1. Run `--status` again against the same explicitly confirmed database.
2. Verify the ledger has exact filenames and SHA-256 values for 043, 044 and 045.
3. Inspect the migration log and failure ledger.
4. Verify the expected tables, indexes, constraints and trigger objects exist.
5. Confirm API health.
6. Test customer claim submit, own-claim history, cancellation of pending/proof-required claim, denial of another customer's cancellation, and denial of cancellation after review.
7. Test admin claim review/rejection reason, contact verification/revocation rules and relationship revocation audit history.
8. Test customer/staff/vendor authentication regression.
9. Compare counts of source customer/CRM/employee/supplier rows to identity profiles; explain every unlinked or conflicting record. Do not automatically merge candidates.
10. Verify loyalty and referral associations without changing existing balances, cards, ledger rows or referral rewards.
11. Verify backend and both relevant frontend releases independently; check storefront and admin browser smoke tests.

## 10. Application deployment and ordering

Use the repository's approved GitHub Actions release workflows. The current deploy workflow is push-triggered on every `main` update, so do not create a new main push merely to initiate deployment. Inspect the exact run, target environment, skipped/conditional jobs and rollback behavior. The documentation-push incident above demonstrates this trigger.

Recommended sequence:

1. Complete the schema preflight and review.
2. Apply the approved additive migrations using the controlled runner.
3. Deploy backend code compatible with the new schema.
4. Deploy the storefront/admin frontend artifacts that include the identity UI.
5. Run production smoke and regression checks.
6. Record release SHA, workflow run IDs, database migration ledger evidence, backup name, logs and operator approval.

If the current deployment workflow applies migrations automatically, stop and reconcile that behavior with this runbook before triggering it. Avoid duplicate or concurrent migration execution.

## 11. Stop / rollback conditions

Stop the release if:

- The live database name, host, role or checkout differs from the approved values.
- The effective schema timer is configured to apply rather than status-check.
- A required migration file is missing, has a duplicate prefix or differs from its applied checksum.
- Backup verification fails or no recovery plan exists.
- A required migration fails or the runner returns a stop code.
- Authentication, customer claim ownership, admin RBAC or audit history tests fail.
- Existing loyalty/referral/accounting/customer data appears changed unexpectedly.

Application rollback and database rollback are not the same operation. Do not restore a pre-migration dump over production without an explicit database-owner decision, impact assessment and recovery plan. Prefer forward-compatible application rollback where schema compatibility permits.

## 12. Release evidence record

Record the following for each production rollout:

| Evidence | Value to record |
|---|---|
| Approved main SHA | |
| Backend workflow run and deployed artifact | |
| Storefront/admin workflow run and deployed artifact | |
| Production host and database confirmed | |
| Effective schema service/timer configuration checked | |
| Pre-migration backup filename and validation | |
| 043 ledger filename/checksum/applied time | |
| 044 ledger filename/checksum/applied time | |
| 045 ledger filename/checksum/applied time | |
| Post-migration status and logs | |
| API/browser smoke-test results | |
| Reconciliation counts and exceptions | |
| Approver/operator and approval timestamp | |

**No production rollout is complete until this record is populated with actual evidence.**
