# Database change rules (MUST READ before touching the database)

Applies to every person and every AI (Claude, ChatGPT, Codex, anyone). If you cannot read this file, stop and tell the owner.

## 1. When this file applies

Read it BEFORE any change or advice that involves:
- creating, changing or removing a table, column, index, constraint, trigger, view or role/permission;
- changing or copying data, backfills, imports, clean-ups, resets;
- any file in `backend/schema/`, `backend/schema_required.txt`, or the scripts `backend/scripts/apply_schema.sh` (migration runner), backups, deploy or sync scripts;
- code that starts using a new table or column, or runs SQL that changes data;
- login, registration, customers, orders, payments, loyalty (the data that must never be damaged).

Not sure if it applies? It applies.

## 2. Who does what (hard rule)

| Work | Owner |
|---|---|
| All SQL: schema files, migrations, indexes, constraints, backfills, DB permissions | **Database Owner** |
| Migration runner, backup scripts, drift-check tooling, `schema_required.txt`, CI database check | **Database Owner** |
| Database review and migration review | **Primary Reviewer (Claude when available), Secondary Reviewer (ChatGPT)** |
| Application code (FastAPI, frontend, validation, tests, UI) | Any approved contributor |
| Running production actions, merge approvals, deployment approvals | **Repository Owner** |

The Database Owner retains final authority for all database decisions. Reviewers may recommend changes but may not bypass owner approval.

### Database Governance Roles

**Repository Owner**
- Final authority for all repository decisions.
- Final authority for all production database decisions.

**Database Owner**
- Owns schema design.
- Owns migration numbering.
- Owns migration review process.
- Owns schema compatibility decisions.
- Approves database changes before merge.

**Primary Reviewer**
- Claude (when available).
- Reviews migration safety and compatibility.

**Secondary Reviewer**
- ChatGPT.
- Reviews migration safety, compatibility and implementation impacts.

Reviewers provide recommendations only. The Repository Owner and Database Owner remain responsible for final approval. In this repository's current governance model, the Repository Owner and Database Owner are the same person.

If you are not the Database Owner and need a database change: do NOT write the SQL or modify protected database assets. Fill in the "Database Change Request" (section 9) and give it to the owner for approval and assignment. Writing unapproved SQL is how this project broke before.

## 3. Facts that must never be guessed

- Production database name is `sb_app`. Backend listens on `127.0.0.1:8001`. PostgreSQL port `5432`. (README)
- The old runner script contained `superbajaar` and port `8000`. Those are wrong; use the values above.
- Applied files are recorded in the table `schema_migrations` (file name + checksum). Failures are recorded in `schema_migration_failures`.
- Protected files, never edit, rename, delete or reformat: `000_baseline_schema.sql`, `009_loyalty_programme.sql`, and any file that may already be applied. Two numbers are used twice (`009` and `012`); both pairs are allowed and must not be renamed. Order is by full file name.
- Whether a file is applied on the server is only known from the server's ledger, never from Git. Ask the owner to run the check in section 8.

## 4. Rules for schema files

1. Never edit an existing schema file once it may have been applied. Any correction is a NEW file with the next unused number (check the folder AND the ledger).
2. One new schema file per change. Do not bundle unrelated changes.
3. Additive and repeatable only: `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ON CONFLICT DO NOTHING`. Running it twice must change nothing.
4. Forbidden on production: `DROP`, `TRUNCATE`, `DELETE`/`UPDATE` without a reviewed WHERE and a backup, column type changes that rewrite data, renaming tables or columns used by running code.
5. No `BEGIN`/`COMMIT` inside a file (the runner wraps each file in a transaction) and no `CREATE INDEX CONCURRENTLY`.
6. New unique rules must first be checked against live data (a read-only duplicate query is included in the change request). A unique index on data that already has duplicates fails the deploy.
7. Unique means unique inside one table for one purpose. One person can be a customer, employee, vendor, seller and partner, so a mobile number must never be made globally unique across roles. Customer mobile uniqueness applies to `customer_accounts` only.
8. Table names are lowercase with underscores. File names are `NNN_short_name.sql`, lowercase.
9. Test on a scratch Postgres 15 and 16 (twice, in order) before the pull request. Do not claim a pass without having run it.
10. If application code needs the new table or column, add that schema file to `backend/schema_required.txt` in the same pull request.
11. The migration runner must never grant blanket privileges on all tables or sequences in `public`. If the application needs access to objects created by a migration, that migration must declare explicit, least-privilege `GRANT` statements for only those objects and the intended application role. Do not use `GRANT ... ON ALL TABLES/SEQUENCES IN SCHEMA public`.
12. `000_baseline_schema.sql` is a one-time bootstrap for an empty database, not a repair script. If it is not recorded in `schema_migrations` while user objects already exist, the runner must stop before backup or schema changes. Never mark it applied manually just to bypass this guard.

## 5. How the safe deploy works (so nobody breaks it)

`apply_schema.sh <schema_dir>` does, in order: checks the database and migration ledger, refuses to bootstrap the baseline over an existing database, reads every file, takes and verifies a backup (no backup = no change), applies each new file in its own transaction (a failed file changes nothing), records every result, and alerts on any failure. It does not grant application-role permissions automatically; any required access must be explicitly and narrowly declared in the migration. A failed file is not retried until its content changes. Independent later files still apply.

Exit codes: `0` all good. `11` some file failed but every required file is applied (deploy may continue). `10` something failed and no required list exists (do not deploy). `20` a required file is missing (do not deploy; the old release stays live). `30` backup failed, nothing changed. `50` setup problem. `60` another run in progress.

The deploy continues only on `0` or `11`. Never change this behaviour, the exit codes, the backup step or the checksum rule without approval from the Database Owner and Repository Owner.

## 6. Rules for application code that touches the database

- No schema changes (`CREATE`, `ALTER`, `DROP`) in application code.
- A feature that needs a possibly-missing table must catch the error and fail only that feature, with a clear message, never the whole site.
- Wrong or hostile input (someone else's mobile number, repeated tries) must end in a clean error and change nothing: validate input, use one generic message for duplicates, rate-limit register and login, and keep each write inside one transaction.
- Never reveal whether an email or mobile number is already registered.

## 7. Before you start any database work: checklist

1. Read this file and the README safety section.
2. List `backend/schema/` and read the files that touch the same tables.
3. Ask the owner for the live checks in section 8 if the task depends on live state.
4. Write the Database Change Request (section 9) or, if you are the Database Owner, prepare the proposed new schema file for review.
5. Test twice on scratch Postgres 15 and 16. Open a pull request using the template. Never push to `main`.
6. The owner merges. The deploy applies the file. The owner confirms with `--status`.

## 8. Live checks the owner can run (read-only)

```
sudo -u postgres psql -c "\l"                                  # which database names exist
sudo -u postgres psql sb_app -c "SELECT filename, applied_at FROM schema_migrations ORDER BY applied_at DESC LIMIT 15;"
sudo -u postgres psql sb_app -c "\d customer_accounts"         # replace with the table in question
bash backend/scripts/apply_schema.sh backend/schema --status   # state of every file
tail -n 100 /home/ec2-user/deploy/schema.log
ls -lh /home/ec2-user/schema-backups/ | tail
```
Never paste passwords, keys or `.env` contents.

If the Primary Reviewer needs historical implementation context, it will ask the owner, who may ask another reviewer and relay the answer. Guessing is not allowed.

## 9. Database Change Request (template for contributors other than the Database Owner)

```
DATABASE CHANGE REQUEST
What the feature or bug needs (plain words):
Tables/columns involved:
Code that will use it (file names):
Should one person be allowed several roles? (customer/employee/vendor/partner):
Existing data that must be preserved:
Live data checks I could not do (owner to run):
Does the code require this change before it can deploy? (yes/no):
```

## 10. Release gates

Before merge, the owner must enable GitHub main-branch protection requiring both PostgreSQL matrix checks and up-to-date branches. Before production deployment, the owner must complete the read-only production preflight and confirm the live ledger/checksums and backup readiness. See `docs/RELEASE_GATES.md`. CI success alone is not production approval.

## 11. Definition of done

A database change is done only when: the schema file passed twice on scratch Postgres 15 and 16, the CI check is green, the owner merged it, the runner log shows it applied, `--status` shows it as APPLIED, and the feature works on the live site. Anything else is "not done".
