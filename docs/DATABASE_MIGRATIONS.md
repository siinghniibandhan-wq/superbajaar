# Database migrations and operations

This document is the operational reference for PostgreSQL schema changes in Super Bajaar. It describes the committed migration runner and the production arrangement reported and verified by the project owner on 10 November 2026. It does not authorize a production migration.

## 1. Production database identity

The production database is a self-managed PostgreSQL instance on the Super Bajaar EC2 host. It is **not Amazon RDS**.

| Setting | Production value |
|---|---|
| Database | `superbajaar` |
| Application role | `superbajaar_app` |
| PostgreSQL port | `5432` |
| Database host | `127.0.0.1` (localhost only) |
| Repository checkout | `/opt/superbajaar/source` |
| Schema directory | `/opt/superbajaar/source/backend/schema` |
| Migration runner | `/opt/superbajaar/source/backend/scripts/apply_schema.sh` |
| Required migration list | `/opt/superbajaar/source/backend/schema_required.txt` |

The runner defaults to `SB_DB=sb_app` if `SB_DB` is omitted. That historical default is **not** the production database. Always set `SB_DB=superbajaar` explicitly for production commands. Never infer the target database from the runner default.

The PostgreSQL service is local to the EC2 host. Keep it private; do not expose port 5432 publicly or replace this arrangement with RDS as part of a migration task.

## 2. Automatic status check versus manual application

The production schema systemd service and timer are configured for **status-only checks**. The timer runs every two minutes. The service invokes the runner with `--status`; it must not run the runner in its default apply mode.

Production service configuration supplied by the project owner:

- Unit: `/etc/systemd/system/superbajaar-schema.service`
- Drop-in: `/etc/systemd/system/superbajaar-schema.service.d/override.conf`
- Timer: `/etc/systemd/system/superbajaar-schema.timer`
- Effective runner invocation must end with:
  `/opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema --status`
- Explicit environment includes `SB_DB=superbajaar`, `SB_PSQL=/usr/local/bin/sb-psql`, `SB_BACKUP_DIR=/var/lib/superbajaar/backups`, and `SB_LOG=/var/log/superbajaar/schema.log`.

The intended status-check semantics are that exit code 10 means migration attention is required; it is not equivalent to a clean schema. However, the read-only EC2 diagnostic on 12 November 2026 inspected the merged unit with `systemctl cat` and did **not** show `SuccessExitStatus=0 10` in either the base unit or its drop-in. The installed service therefore treated exit code 10 as a failed oneshot (`Result=exit-code`). Do not assume the documented success-exit override is installed; verify the effective unit on the host. Keep this alert-visible behaviour until the operator explicitly chooses and documents a different monitoring policy.

Do not remove `--status` from the effective `ExecStart`. The runner's default mode (no option) applies pending SQL. A timer running without `--status` can therefore make database changes automatically.

Useful server-side checks:

```bash
sudo systemctl cat superbajaar-schema.service
sudo systemctl cat superbajaar-schema.timer
sudo systemctl status superbajaar-schema.timer
sudo systemctl list-timers --all | grep superbajaar-schema
sudo systemctl status superbajaar-schema.service
sudo journalctl -u superbajaar-schema.service --since "24 hours ago"
sudo tail -n 200 /var/log/superbajaar/schema.log
```

Confirm that the effective service command includes `--status`. A base unit alone is not sufficient evidence when a drop-in override exists; inspect the merged unit with `systemctl cat`.

## 3. Controlled manual migration procedure

A migration is a separately approved database operation. A Git commit, CI run, timer tick or status report does not authorize applying SQL to production.

Before any production apply:

1. Review the complete SQL diff and its dependencies.
2. Confirm the migration filename is unique and follows the numbering rules below.
3. Confirm the migration is included in `backend/schema_required.txt` if the release depends on it.
4. Verify the current migration status against the intended production database.
5. Run the dry-run and review its output.
6. Confirm a fresh, verified backup and a recovery plan.
7. Obtain explicit approval for the production apply.

Run these commands on the production host from the approved checkout. They explicitly identify the production database and the configured client, backup and log paths.

Check status:

```bash
sudo env SB_DB=superbajaar SB_PSQL=/usr/local/bin/sb-psql SB_BACKUP_DIR=/var/lib/superbajaar/backups SB_LOG=/var/log/superbajaar/schema.log \
  /bin/bash /opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema --status
```

Preview pending work without applying:

```bash
sudo env SB_DB=superbajaar SB_PSQL=/usr/local/bin/sb-psql SB_BACKUP_DIR=/var/lib/superbajaar/backups SB_LOG=/var/log/superbajaar/schema.log \
  /bin/bash /opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema --dry-run
```

Only after the review, backup verification and explicit approval, apply:

```bash
sudo env SB_DB=superbajaar SB_PSQL=/usr/local/bin/sb-psql SB_BACKUP_DIR=/var/lib/superbajaar/backups SB_LOG=/var/log/superbajaar/schema.log \
  /bin/bash /opt/superbajaar/source/backend/scripts/apply_schema.sh /opt/superbajaar/source/backend/schema
```

The apply command intentionally has no mode flag: no option is the runner's apply mode. Never put that invocation in the automatic timer.

After an approved apply, run `--status`, inspect the migration log and service health, and confirm the expected ledger entries and schema state. Do not claim success solely because the command returned or the service timer ran.

## 4. Runner safeguards and migration ledger

The runner is `backend/scripts/apply_schema.sh`. Its current implementation provides these safeguards:

- Checks database connectivity, schema directory, migration filenames and duplicate three-digit prefixes before applying.
- Uses a lock to prevent concurrent runner executions.
- Refuses to guess when a populated database has no migration ledger or when the ledger shape is unexpected.
- Checks `backend/schema_required.txt` against files in the schema directory.
- Creates a custom-format `pg_dump` backup before applying pending SQL and verifies it with `pg_restore --list`. If backup verification fails, it exits without applying SQL.
- Applies each pending SQL file in its own transaction.
- Records successful files and SHA-256 checksums in `schema_migrations`.
- Records failed attempts in `schema_migration_failures`.
- Detects an applied migration whose contents have changed and does not silently reapply it.
- Does not automatically retry an unchanged known failure unless the explicit retry mode is used.

The migration ledger is evidence of what was applied to that particular database. It is not a list to be edited to make production resemble a fresh installation. Never invent, delete, rewrite or manually insert migration history to resolve a filename conflict.

### Runner exit codes

| Code | Meaning |
|---:|---|
| 0 | All schema files are applied; no issues reported |
| 10 | Status/dry-run attention, or problems with no required-list configuration; inspect output |
| 11 | Problems exist, but every required migration is applied |
| 20 | A required migration is not applied; release must be blocked |
| 30 | Backup failed; no migration was applied |
| 50 | Setup, connection, filename, ledger or other preflight problem |
| 60 | Another migration runner holds the lock |

The script's comments state that deployment should continue only on 0 or 11. In production, treat 20, 30, 50 and 60 as stop conditions. A status-mode exit code 10 indicates attention is needed; it is not an apply failure and does not itself mean the required release gate is missing.

## 5. Migration filename and immutability rules

All versioned application schema SQL files belong in `backend/schema/`. The filename format is:

```text
NNN_lowercase_description.sql
```

Rules:

- Inspect the full schema directory and target-branch history before choosing a prefix.
- Every three-digit prefix must be unique. Never create two files with the same prefix.
- Do not renumber to fill historical gaps. The sequence is versioned, not required to be gap-free.
- Never edit, rename, move or delete a migration that has been applied or released as part of the migration history.
- A correction to an already-applied migration must be a new, unused numbered migration, after reviewing the database state and obtaining approval.
- Keep SQL files limited to database schema/data changes. Do not put shell scripts, systemd configuration, CI workflows or deployment tooling in SQL files.
- Test migrations against disposable PostgreSQL databases before proposing production use.

The CI migration governance workflow and `docs/SCHEMA_MIGRATION_CRITICAL_RULE.md` provide additional repository-side controls. CI checks must actually run and pass; a workflow file existing in Git is not proof that branch protection enforces it.

## 6. Unified Identity System migrations 043–045 (12 November 2026)

The Unified Identity System code is merged into `main` through PRs #54, #55, #57 and #58. The required release list contains all three identity migrations:

| File | Purpose |
|---|---|
| `043_unified_identity_foundation.sql` | Adds identity parties, typed profiles, authentication-account links, contacts, relationships, link requests, events and aliases |
| `044_identity_loyalty_referral_links.sql` | Adds representative metadata to portal invitations and association tables for existing loyalty accounts and referral records |
| `045_identity_claim_cancellation_event.sql` | Adds the `link_cancelled` event type to the identity audit-event constraint |

All three filenames are present in `backend/schema_required.txt`. Their SQL is additive. Migration 044 explicitly preserves existing loyalty accounts, cards, balances, ledgers, referral codes and rewards; it does not perform a historical data backfill. Migration 045 only changes the permitted identity event types.

**Source status:** merged into GitHub `main`.  
**Production migration status:** not verified by the repository commit. Confirm the intended production database ledger and schema before calling these migrations applied.

The current schema directory contains 40 SQL migration files, with unique prefixes through 045. Do not infer that all 40 are applied in production from their presence in Git.

See [Unified Identity System implementation](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md) and its [production rollout runbook](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md).

## 6.1 Baseline checksum reconciliation — open preflight item

The 12 November 2026 production preflight record reports that `000_baseline_schema.sql` does not match the checksum recorded in the production migration ledger. This is a release-blocking reconciliation item until the exact production ledger value, repository blob and host file have been compared and the approved immutable baseline has been restored or a documented recovery decision has been made.

Required handling:

1. Do not edit the production `schema_migrations` ledger or manually replace its checksum.
2. Do not rewrite the historical baseline to match a drifted host copy.
3. Compare the baseline Git blob, the file on the production checkout and the checksum recorded for the baseline in the production ledger.
4. Preserve the verified original baseline and its provenance; if the repository copy is incorrect, restore the exact approved immutable blob through a reviewed PR.
5. Re-run source/baseline preflight and record the evidence before any production migration apply.

The previously recorded production preflight identifies migrations 043 and 044 as applied and 045 as pending, while also flagging this baseline checksum mismatch. Reconfirm all of these facts against the current production ledger before acting. Migration 045 remains subject to separate production approval and readiness checks.

## 7. Historical duplicate-036 reconciliation (10 November 2026)

Two different migration files historically used prefix `036`:

- `036_super_admin_role.sql` — a historical migration that was applied in production at 11:24 UTC and later removed from the repository.
- `036_configurable_rbac.sql` — the current canonical migration retained in `backend/schema/`, applied in production at 16:02:07 UTC.

The project owner confirmed a production backup named `superbajaar-pre-migration-20261110T160206Z.dump`, created at 16:02:06 UTC before the second migration ran. The owner confirmed that `pg_restore --list` could read the backup.

The repository reconciliation is:

- Keep `036_configurable_rbac.sql` as the only current repository file with prefix `036`.
- Do not restore `036_super_admin_role.sql` to the current schema directory.
- Do not edit or rename `036_configurable_rbac.sql`.
- Do not create a replacement `037` migration merely to erase the historical duplicate.
- Preserve both historical production ledger records as historical facts. Do not delete or fabricate ledger entries.
- Fresh installations use the current repository migration set; production retains its actual migration history. The two ledgers may therefore differ historically even though the current repository has only one `036` filename.

This is a documented historical migration-history exception, not a reason to alter applied SQL or production ledger records. The current `backend/schema_required.txt` list does not include `036_configurable_rbac.sql`; do not silently change that release-gate policy as part of documenting this incident. Any future decision to make it release-required must be reviewed as a separate change.

## 8. Backup and recovery discipline

Before any approved production migration, confirm the backup destination has sufficient space and that the resulting dump is non-empty and readable by `pg_restore --list`. Retain the exact backup identifier and timestamp in the change record.

If a migration fails, stop and inspect the runner log, failure ledger, database state and backup. Each migration runs in its own transaction, but do not assume that this makes every multi-file release automatically reversible. A restore is a database-owner operation and must use a reviewed recovery plan. Do not restore an older dump over production without explicit authorization and an impact assessment.

The confirmed 10 November backup above is historical evidence for that migration event; it is not proof that a current backup exists for a future change.

## 9. Related files

- `backend/schema/` — versioned PostgreSQL schema SQL.
- `backend/schema_required.txt` — release-critical subset of migrations.
- `backend/scripts/apply_schema.sh` — migration runner and modes.
- `backend/scripts/tests/test_apply_schema.sh` — runner tests.
- `docs/SCHEMA_MIGRATION_CRITICAL_RULE.md` — immutable migration filename rule.
- `README.md` — repository overview and migration entry point.


## 8. Verified production migration status — 12 November 2026

A read-only EC2 diagnostic at 06:46 UTC targeted database `superbajaar`, found 40 SQL files and reported:

| Migration / check | Observed production state |
|---|---|
| `000_baseline_schema.sql` | Failed/changed: current file checksum differs from the checksum recorded when it was applied; runner reports `changed after it was applied; not re-applied` |
| Migrations `043` and `044` | Applied and marked required |
| Migration `045_identity_claim_cancellation_event.sql` | Pending and marked required |
| Status runner exit code | `10` — attention required |
| Schema timer | Active and waiting |
| Schema service | Last run failed with exit code `10` |
| Effective schema command | Explicitly includes `--status`; no SQL apply was run |

The installed schema service's effective command was confirmed through `systemctl cat` and included the explicit production target (`SB_DB=superbajaar`) and `--status`. The service is therefore configured as a read-only status check in this snapshot. Its non-zero status is reporting the database attention condition; it is not evidence that the timer applied SQL.

### Required reconciliation and release block

The baseline checksum mismatch is the first database blocker. Before attempting migration 045 or any other production apply:

1. Compare the exact Git blob for `000_baseline_schema.sql`, the EC2 checkout file and the SHA-256 recorded in the production `schema_migrations` row.
2. Establish which immutable baseline version was originally applied and preserve its provenance and backup evidence.
3. If the repository baseline is wrong, restore the approved historical blob through a reviewed change. If the production host file alone is wrong, correct the source checkout through the normal reviewed Git process.
4. Re-run read-only source/baseline verification and `--status`; record the outputs.

**Never** update, delete or insert rows in `schema_migrations` merely to silence the mismatch. Never reapply the baseline. Never use `--retry` for this changed-applied-file condition as a substitute for checksum reconciliation.

Migration 045 remains pending. Its presence in Git and in `schema_required.txt` does not authorize production application. It requires a separate explicit production approval after the baseline blocker is resolved and backup/readiness checks pass.

The schema timer and service should continue to be treated as a status-monitoring mechanism only. Keep `--status` in the effective service command. Do not change the service to default/apply mode to make the status exit code green. A systemd service failure at exit code 10 is the current observed alert behaviour; inspect the runner output and logs to understand the actual migration state.

This snapshot is evidence from 12 November 2026 at approximately 06:46 UTC. Re-run the checks before any later production operation; do not treat this dated status as live indefinitely.


## 10. Production baseline checksum reconciliation (12 November 2026)

A read-only production comparison identified the exact historical version of `000_baseline_schema.sql` recorded in the production migration ledger. The database ledger checksum is:

```text
519e4467a6af9c1f87dd06cbdb80ef4545b1ae04edfe8937966799792168d938
```

The checksum matches the historical file content in commits `12350a4513d2ddbf5f9107eb3f15625557e16b5a`, `3a5a0cf8bd63cd0d99f9f1e1b42dd1b388fd74a4` and `881f2e09beddf6f0a22b5ca6365e500ca81dadde`. The corresponding Git blob is `74cfc166c80b815186035abe61322efd5905575f`. The later baseline blob `54ccd721461682cf6d5349bf84a8767420544668` has SHA-256 `f95b15efed9e49e11e85bcf1786ae89ff10d29a60bb44774eedca3d82813a578` and does not match production.

The baseline was changed to include `super_admin` in the `app_users_role_check` constraint. That was the wrong place for this role change: the already-versioned `036_configurable_rbac.sql` migration creates the Super Admin role and updates the constraint as part of the RBAC rollout. The baseline must remain the original production-matched schema snapshot. Restore it byte-for-byte; do not edit the production ledger, reapply the baseline, or add a second baseline migration.

The schema-governance workflow permits this one recovery only when both the exact historical Git blob and its SHA-256 match the production-pinned values above. Every other edit to an existing migration remains prohibited. The baseline restoration is a repository correction, not a production database operation.

**Production status at the time of comparison:** the status-only runner reported the baseline checksum mismatch, migrations 043 and 044 applied, and required migration 045 pending. No migration was applied during this comparison. Re-run the read-only status check after the repository sync to verify that the mismatch is resolved. Migration 045 still requires its separate production approval and readiness checks.


## 11. Historical failure checksum reporting correction (12 November 2026)

The production baseline reconciliation was verified read-only on EC2 after commit `84a3792a675d0587d51db4acd1a4c0fd4ac3e7d3` reached `main`. The checked-out baseline SHA-256 and the production `schema_migrations` checksum both equal:

```text
519e4467a6af9c1f87dd06cbdb80ef4545b1ae04edfe8937966799792168d938
```

The production failure table retains an older audit record for the same filename with checksum `f95b15efed9e49e11e85bcf1786ae89ff10d29a60bb44774eedca3d82813a578`. This record describes the superseded baseline content and is not an active failure for the restored file. The runner correctly classified the baseline as APPLIED, but its status output previously printed the latest failure by filename alone, which made the old record look current.

The runner now reports failure details only when the failure record's filename **and checksum** match the current schema file. Historical rows are preserved in `schema_migration_failures` for audit; no production ledger or failure rows are deleted or edited.

Read-only production status after the source sync confirmed:
- `000_baseline_schema.sql`: APPLIED; current file checksum matches the applied ledger checksum.
- Migrations 001–044: APPLIED.
- `045_identity_claim_cancellation_event.sql`: PENDING and required.
- Status exit code: 10 because migration 045 remains pending; this is not a baseline failure.

This repository correction changes reporting only. It does not apply SQL, retry migrations, alter the production ledger, change systemd configuration, or authorize migration 045. The pending migration still requires separate review, readiness checks and explicit production approval.


---

## 11. Authoritative production update — 12 November 2026

This dated section supersedes earlier point-in-time statements in this file that identify migration 045 as pending. The following is the production state reported and verified by the owner on 12 November 2026; re-run read-only checks before a later database operation.

### Migration 045

| Field | Result |
|---|---|
| File | `045_identity_claim_cancellation_event.sql` |
| State | Applied and verified |
| Migration ledger count | 41 |
| SHA-256 | `874886ce7aae2bc6c4f541e95f63bf231ac06b187a62aeb94cef6f58cbf2b948` |
| Constraint | Includes `link_cancelled` |
| `identity_events` rows | 0 at verification time |

Do not reapply migration 045. A zero-row event table is an observed data count, not evidence that the migration failed.

### Verified pre-045 recovery artifact

- File: `superbajaar-pre-045-20261112T085030Z.dump`
- Location: `/var/lib/superbajaar/backups` on the EC2 instance
- SHA-256: `de8fadf361d29e195c37a75a7fc08b17fbd185c0a2793cda309422635d44b24e`
- Owner reports the dump is restorable.

The owner reports that a zero-byte dump was removed and the new dump and checksum file were assigned to `ubuntu`. The dump is on instance storage. **No off-instance mechanism was observed**; this does not establish that EBS snapshots, DLM, AWS Backup or S3 copies are absent. Those services and retention settings remain to be inspected.

### Migration change control

Migration numbering remains unique and immutable. Keep SQL files limited to schema/data changes. Do not renumber, edit or delete applied migrations. The status-only timer is not an apply authorization. Any future production migration still requires a reviewed change, fresh verified backup, explicit production approval and post-apply ledger/schema verification.

For the consolidated current owner decisions, IAM/self-review risk, rollback design and open infrastructure checks, see [Production governance and readiness](PRODUCTION_GOVERNANCE_AND_READINESS.md).
---

## 12. Production migration reconciliation — 12 November 2026

This dated section records the read-only production checks supplied from EC2 on 12 November 2026. It supersedes earlier sections in this file that report migration 045 pending or the baseline checksum mismatch as current. Those earlier sections remain historical snapshots.

### Current production migration state

| Check | Observed result |
|---|---|
| Database | `superbajaar` |
| Current SQL files | 40 |
| Production ledger rows | 41 |
| Runner status | All 40 current files APPLIED |
| Runner exit code | 0 |
| Migration 045 | APPLIED |
| Schema timer | `superbajaar-schema.timer`, enabled and active |
| Timer schedule | Every 2 minutes |
| Last observed oneshot status service | `superbajaar-schema.service`, exit 0 / SUCCESS |

The 41st ledger row is explained by historical migration `036_super_admin_role.sql`, which was applied and later removed from the active repository migration directory. Git history confirms:

- `7308938e7a811a4486079a65c8e6e11d82615103` — “Add Super Admin role and secure provisioning”.
- `5dbe8cf2a1ee9602953f92bce1cee60897a2c67` — “Remove separate Super Admin role migration”.

The current directory contains only `036_configurable_rbac.sql` for prefix 036. A scan of current SQL filenames found no duplicate numeric prefixes. The production ledger correctly retains both historical records. Do not delete ledger rows, restore the removed file into the active migration directory, or rename/edit either applied migration. This is a historical migration-history exception, not a current duplicate-number violation.

### Baseline checksum reconciliation

The current `backend/schema/000_baseline_schema.sql` SHA-256 and production `schema_migrations` row match exactly:

```text
519e4467a6af9c1f87dd06cbdb80ef4545b1ae04edfe8937966799792168d938
```

The failure table retains one historical record for the baseline with SHA-256:

```text
f95b15efed9e49e11e85bcf1786ae89ff10d29a60bb44774eedca3d82813a578
```

Its error is `changed after it was applied; not re-applied`. This record refers to older superseded file content. The current baseline is APPLIED and checksum-matched; the old failure record is retained for audit and must not be deleted or rewritten.

### Migration 045

| Field | Value |
|---|---|
| Filename | `045_identity_claim_cancellation_event.sql` |
| State | APPLIED |
| Ledger SHA-256 | `874886ce7aae2bc6c4f541e95f63bf231ac06b187a62aeb94cef6f58cbf2b948` |
| Required manifest | Included in `backend/schema_required.txt` |

Do not reapply migration 045.

### Timer naming and behaviour

The installed unit names are `superbajaar-schema.timer` and `superbajaar-schema.service`. The timer is enabled/active and configured with `OnCalendar=*:0/2`. The service is a static oneshot that explicitly runs the runner with `--status`. Its state `inactive (dead)` after a successful run is normal oneshot behaviour; the timer remains active. The similarly named `sb-schema.timer` does not exist on the host. The timer is a status monitor, not an automatic migration-apply mechanism.

### Operational safeguards

- Preserve the historical baseline failure row and both historical 036 ledger rows.
- Do not renumber, edit, rename or delete applied migration files.
- Keep the current migration directory's unique numeric prefixes.
- Do not change the status timer into apply mode.
- A future production migration still requires a reviewed migration, a fresh verified backup, separate explicit production approval and post-apply verification.

No SQL was applied and no ledger/failure rows were modified during this audit.


---

## 13. AWS-native schema apply lane — 13 November 2026

**Current operating model (owner-supplied configuration):** This section supersedes the earlier status-only timer and manual-only application descriptions above. Those sections preserve the previous operating model and dated evidence. The current configuration below was supplied by the project owner on 13 November 2026; this documentation update did not independently inspect the live EC2 units or execute a migration.

### Timer and service

| Setting | Current supplied value |
|---|---|
| Timer | `superbajaar-schema.timer` |
| Schedule | `OnCalendar=*:0/2` — even minutes, every 2 minutes |
| Service user | `ubuntu` |
| Service override | `/etc/systemd/system/superbajaar-schema.service.d/override.conf` |
| Previous override backup | `override.conf.bak-20261113T002237Z` |
| Runner | `/opt/superbajaar/source/backend/scripts/apply_schema.sh` |
| Mode | APPLY (no `--status` argument) |
| Failure policy | `SB_ON_FAILURE=stop` |
| Post-run hook | `sb-db-lane-post.sh` copies new backups to S3 and ships new log lines |

The schema lane runs independently of the backend deployment lane. It does not restart the backend. Its post-run hook handles backup/log shipping.

### Migration transaction and safety contract

The deployed runner is reported as v2 and compares `backend/schema/*.sql` against `schema_migrations` using filename and SHA-256.

1. A new eligible file must pass filename, numbering, duplicate-table and ledger checks.
2. A verified database backup is required before any schema change. If backup creation or verification fails, no migration is applied.
3. Each SQL file and its migration-ledger record are committed together in one transaction.
4. A failed migration is rolled back, recorded in `schema_migration_failures`, and not retried while its content/checksum remains unchanged.
5. An already-applied file whose contents have changed is reported and never reapplied.
6. With `SB_ON_FAILURE=stop`, processing stops at the first failed file.
7. The lane uses the lock `/tmp/sb_schema.lock`; a concurrent run is not allowed to apply in parallel.
8. It stops on duplicate numeric prefixes, invalid names (must be `NNN_name.sql`), or a table name found in more than one schema.
9. A post-apply health check targets `http://127.0.0.1:8001/api/health`. The schema lane never restarts the backend.

### Backups and retention

- Local directory: `/var/lib/superbajaar/backups`.
- Local retention: 14 days, while retaining at least the 3 newest backups.
- The post-run hook copies new backup artifacts to the private S3 bucket:
  `superbajaar-db-backups-715975223136-715975223136-us-east-1-an`.
- The supplied bucket configuration includes a 30-day expiration lifecycle rule.
- Do not interpret the configured S3 lifecycle as a substitute for verifying that each upload succeeded and that the object is readable.

### Exit-code reference

| Code | Meaning |
|---:|---|
| 0 | Successful/no outstanding issue |
| 10 / 11 | Migration or integrity problems reported |
| 20 | Required migration file blocked/missing; dependent backend release must wait |
| 30 | Backup failed; no schema change |
| 50 | Setup/configuration problem |
| 60 | Another run holds the lock |

### Release dependency

If a backend commit requires a new schema file, the same commit must add that exact filename to `backend/schema_required.txt`. The backend lane waits until every required filename at the target commit is present in `schema_migrations`. Keep migration files additive and immutable after application; never edit, rename or delete an applied migration. Choose the next unused number after inspecting the full migration directory and ledger/history.

### Read-only status and emergency controls

The following commands are observational only:

```bash
systemctl list-timers --all | grep superbajaar
tail -n 30 /var/log/superbajaar/schema.log
curl -s http://127.0.0.1:8001/api/health
```

Stop the schema lane:

```bash
sudo systemctl disable --now superbajaar-schema.timer
```

Re-enable it:

```bash
sudo systemctl enable --now superbajaar-schema.timer
```

Do not use the emergency commands casually; disabling a timer pauses the automated migration lane but does not undo migrations already committed to PostgreSQL. Confirm the current service unit and timer state before acting.
