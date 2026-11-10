# Super Bajaar SQL Schema Automator — Findings and Specification

**Document date:** 10 November 2026  
**Status:** Discovery record; timer configuration and production migration execution are not complete  
**Scope:** PostgreSQL schema migration automation on the existing EC2 host  
**Out of scope:** GitHub code-pull/deployment automation

This document records the live-environment details observed during the SQL Schema Automator investigation. It distinguishes confirmed facts from items that still require verification. It is not authorization to apply the pending SQL files.

## 1. Objective

Operate the existing SQL migration runner automatically every two minutes, while preserving its database safety controls.

The automation must:
- Inspect the configured schema directory for eligible numbered SQL files.
- Enforce the existing filename and unique-numbering rules.
- Compare SHA-256 checksums with the migration ledger.
- Take and validate a database backup before any migration changes.
- Apply each migration in its own transaction.
- Record successful and failed migrations.
- Prevent overlapping runs.
- Never silently reapply a migration that was edited after application.
- Respect the release's `schema_required.txt` gate.
- Produce observable systemd service and timer logs.

The timer is not to be enabled in apply mode until the pending migration set and its prerequisites have been reviewed and approved.

## 2. Confirmed live backend configuration

The following values were returned by inspection of `superbajaar-backend.service`:

| Setting | Observed value |
|---|---|
| systemd service | `superbajaar-backend.service` |
| Service user | `ubuntu` |
| Service group | `ubuntu` |
| Working directory | `/opt/superbajaar/source/backend` |
| Environment file | `/etc/superbajaar/backend.env` |
| Application executable | `/opt/superbajaar/backend/venv/bin/gunicorn` |
| ASGI application | `app.main:app` |
| Worker class | `uvicorn.workers.UvicornWorker` |
| Workers | `1` |
| Bind address | `127.0.0.1:8001` |
| Timeout | `120` seconds |

The service environment file was observed with mode `0600`, owned by `root:root`. Its credentials are intentionally not recorded here.

## 3. Confirmed PostgreSQL target

The environment file contains a `DATABASE_URL` targeting:

| Setting | Confirmed value |
|---|---|
| Engine | PostgreSQL |
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `superbajaar` |
| Database role | `superbajaar_app` |

The database password is deliberately excluded.

### Database-target mismatch in the runner

The current runner contains:

```bash
DB="${SB_DB:-sb_app}"
```

The live backend's configured database is `superbajaar`, not the runner's fallback `sb_app`. Therefore every scheduled invocation must explicitly set `SB_DB=superbajaar`. Do not rely on the runner's default.

The successful status inspection was invoked with `SB_DB=superbajaar`.

## 4. Migration runner and schema paths

| Item | Confirmed path |
|---|---|
| Existing runner | `/opt/superbajaar/source/backend/scripts/apply_schema.sh` |
| Schema directory | `/opt/superbajaar/source/backend/schema/` |
| Required migration manifest | `/opt/superbajaar/source/backend/schema_required.txt` |

The inspected script identifies itself as **Super Bajaar database change runner, version 2**.

The repository checkout path is `/opt/superbajaar/source`. A Git diagnostic initially encountered Git's “dubious ownership” protection. No global Git safe-directory setting was changed. GitHub synchronization is not part of this workstream.

## 5. Existing runner capabilities

The supplied script already implements the following controls:

| Control | Behaviour in the inspected script |
|---|---|
| Schema directory validation | Refuses to run if the directory is missing |
| Database connectivity | Tests the selected database before proceeding |
| Duplicate table-name check | Stops if same-named user tables exist across non-system schemas |
| Migration filename validation | Requires `NNN_lowercase_name.sql` |
| Unique numbering | Rejects more than one file with the same three-digit prefix |
| Checksums | Calculates SHA-256 for each SQL file |
| Migration ledger | Reads/writes `schema_migrations` |
| Failure ledger | Reads/writes `schema_migration_failures` |
| Baseline safety | Refuses an unrecorded baseline when user objects already exist |
| Required release manifest | Validates files listed in `schema_required.txt` |
| Concurrency protection | Uses `flock` on the configured lock file |
| Backup gate | Requires a non-empty custom-format dump that passes `pg_restore --list` |
| Transaction boundary | Wraps each migration and its ledger insert in its own transaction |
| Failure handling | Records an error and continues to later independent files by default |
| Edited applied file | Reports it and does not reapply it |
| Repeated failure suppression | Does not retry or re-alert an unchanged failed file unless retry is requested |
| Health check | Checks the configured local health URL after migration processing |
| Exit codes | Communicates deployment/migration state through defined exit codes |

### Runner defaults that require operational verification

The inspected script contains these defaults:

| Setting | Script default |
|---|---|
| Database | `sb_app` — must be overridden with `SB_DB=superbajaar` |
| PSQL command | `sudo -n -u postgres psql` |
| PGDUMP command | `sudo -n -u postgres pg_dump` |
| PGRESTORE command | `pg_restore` |
| Backup directory | `/home/ec2-user/schema-backups` |
| Log file | `/home/ec2-user/deploy/schema.log` |
| Required manifest | `$(dirname "$DIR")/schema_required.txt` |
| Health URL | `http://127.0.0.1:8001/api/health` |
| Lock file | `/tmp/sb_schema.lock` |
| Backup retention | 14 days, with at least 3 backups retained |
| Failure policy | `continue` |

**Important permissions concern:** the backend service runs as Linux user `ubuntu`, while the runner's default backup and log paths are under `/home/ec2-user`. The actual existence, ownership and write permissions of these directories have not yet been verified. The migration service must not be enabled until the backup and log paths are confirmed writable by the identity that executes the runner. The dump command runs as PostgreSQL's `postgres` user, while shell output redirection is performed by the runner's user; both sides of that operation must work.

The runner's use of `sudo -n -u postgres` and `pg_restore` must also be validated under the intended systemd service identity, not inferred solely from the successful status check.

## 6. Exit-code contract

| Exit code | Meaning |
|---:|---|
| 0 | All files are applied; no outstanding issue |
| 10 | Migration issue exists and no required manifest is present (strict mode) |
| 11 | Some non-required issue exists, but all required files are applied |
| 20 | At least one required file is not applied; deployment must be blocked |
| 30 | Backup failed; no migration was applied |
| 50 | Setup/configuration/integrity problem |
| 60 | Another runner instance holds the lock |

The `--status` mode can intentionally return 10 when attention is required. A non-zero SSM command result must therefore be interpreted alongside the runner's printed report and exit-code contract.

## 7. Observed migration status on 10 November 2026

A status-only invocation against database `superbajaar` reported:

| State | Count |
|---|---:|
| SQL files discovered | 30 |
| Applied | 0 |
| Pending | 30 |
| Failed files listed in the status output | 0 |
| Changed-after-application files listed | 0 |

All 30 files were shown as pending. The manifest path reported by the runner was:

`/opt/superbajaar/source/backend/schema_required.txt`

The runner's output showed most files marked `[required]`. The status invocation did not apply SQL. Its exit code was 10 because the status mode detected pending files requiring attention.

The migration set observed was:

- `000_baseline_schema.sql`
- `001_loyalty_programme.sql`
- `008_product_category_assignments.sql`
- `009_product_availability_delivery.sql`
- `010_customer_accounts_referrals.sql`
- `011_customer_phone_uniqueness.sql`
- `012_variant_image_primary.sql`
- `013_product_deletion_audit.sql`
- `014_attribute_display_type.sql`
- `015_accounting_ledger.sql`
- `016_product_attribute_custom_options.sql`
- `017_purchasing_lifecycle.sql`
- `018_inventory_cost_layers.sql`
- `019_inventory_batch_provenance.sql`
- `020_hr_workforce_payroll.sql`
- `021_crm_support_workspace.sql`
- `022_hr_statutory_payroll_policies.sql`
- `023_accounting_event_mapping_registry.sql`
- `024_hr_payroll_accounting_accrual_link.sql`
- `025_organisation_policy_foundation.sql`
- `026_inventory_event_approvals.sql`
- `027_inventory_approval_immutability.sql`
- `028_super_coins_checkout_redemption.sql`
- `029_hr_statutory_history_guards.sql`
- `030_super_coins_loyalty_permissions.sql`
- `031_warehouse_fulfilment_operations.sql`
- `032_fulfilment_returns_and_split_dispatch.sql`
- `033_razorpay_webhook_inbox.sql`
- `034_hr_scheduling_leave_lifecycle.sql`
- `035_inventory_facility_internal_locations.sql`

The successful status report means the runner's preflight checks did not reject the target for the conditions tested. It is not a substitute for a full schema compatibility review or a verified backup/restore test.

## 8. Baseline migration review — preliminary

The displayed portion of `000_baseline_schema.sql` describes a proposed schema-only baseline derived from a user-provided dump of a previous `sb_app` database (PostgreSQL 15.19). It explicitly states that it is a draft for review, contains no data, and has no transaction or role-setting statements.

The visible portion includes definitions for application users, categories, customers, stock locations, product attributes, orders, legacy products/orders/users, suppliers, sessions, products, inventory, deliveries, payments, purchasing, support cases, tickets, product attribute values and variants.

Preliminary review points:

1. The baseline's stated source is `sb_app`, while the intended target is `superbajaar`. Confirm that this is the intended schema design for the target; source-database identity alone does not prove compatibility.
2. `CREATE TABLE IF NOT EXISTS` does not reconcile an existing table with a different column, constraint, index or sequence definition.
3. The visible baseline includes both legacy and newer structures, including `products` / `products_legacy` and `orders` / `orders_legacy`. Their intended coexistence and migration path must be checked.
4. The visible `app_users_role_check` allows `owner`, `admin`, `manager`, `staff` and `viewer`, but not `super_admin`. Confirm that a later migration adds the required role safely.
5. The visible `product_attributes_value_type_check` includes several legacy types. Reconcile this with the current catalogue contract before applying the baseline.
6. Only the portion of the baseline returned during inspection has been reviewed here. The complete file and all 29 subsequent migrations still require inspection.

**Baseline decision: not approved for production application at this stage.**

## 9. Proposed two-minute execution model

The intended design is a dedicated systemd oneshot service plus a systemd timer:

```text
systemd timer (every 2 minutes)
          |
          v
schema migration oneshot service
          |
          v
apply_schema.sh <schema-directory>
          |
          v
PostgreSQL database: superbajaar
```

Required properties:

- Explicitly pass `SB_DB=superbajaar`.
- Run under a verified least-privilege Linux identity.
- Use verified backup and log directories with appropriate ownership and permissions.
- Retain the runner's existing lock and backup-before-change gate.
- Do not restart `superbajaar-backend.service` as part of the migration timer.
- Capture and expose the runner's exit codes and logs.
- Ensure expected attention codes (10/11/20/30/50/60) are not silently treated as successful migrations.
- Do not run in apply mode until the pending SQL set has been reviewed and approved.

A two-minute schedule is a polling frequency, not an instruction to create a backup or modify the database every two minutes. When no migration is pending, the runner reports that no new files need applying.

## 10. Work completed versus outstanding

### Completed discovery

- Identified the live backend systemd service and its execution configuration.
- Identified the backend environment file and confirmed its permissions.
- Confirmed the PostgreSQL database target is `superbajaar`.
- Located the existing migration runner, schema directory and required manifest.
- Inspected the runner's implementation and documented its safeguards and defaults.
- Executed status mode against `superbajaar`.
- Captured the complete list of 30 pending migration filenames.
- Confirmed the status check did not apply SQL.
- Identified the mismatch between the runner's default database and the backend's configured database.
- Identified a potential mismatch between the runner's default `/home/ec2-user` backup/log paths and the service's `ubuntu` execution identity.

### Outstanding before enabling the timer

1. Inspect the complete baseline SQL.
2. Inspect all 29 subsequent migrations for ordering, dependencies, duplicate object definitions and compatibility.
3. Confirm the intended target schema design and baseline provenance.
4. Inspect the database's current schemas, objects, roles and migration ledger state without changing them.
5. Verify backup directory and log directory ownership/permissions.
6. Verify `pg_dump`, `pg_restore` and `psql` execution under the proposed service identity.
7. Perform a controlled backup validation and, where feasible, a restore test to a separate test database.
8. Define and install the dedicated systemd service and two-minute timer.
9. Verify timer activation, service execution, lock behaviour, logs and failure reporting.
10. Obtain explicit approval before applying the 30 pending migrations to the production database.

## 11. Explicit scope boundaries

This workstream does not include:

- GitHub polling, automatic pulls or code deployment.
- Frontend deployment or Vercel configuration.
- Backend application code changes.
- Automatic backend restarts.
- Changes to existing business data.
- Unreviewed production SQL execution.
- Rewriting the existing migration runner without a demonstrated defect.

## 12. Definition of done

The SQL Schema Automator is complete only when its target database and execution identity are correct, all migration files and dependencies have been reviewed, backup and restore safeguards have been verified, the two-minute systemd timer is installed, and real timer/service runs are observable and behave correctly.

**Current state:** Existing runner discovered and status inspected; 30 migrations pending; timer not configured or verified; no production migrations applied during this investigation.
