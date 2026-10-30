# Database release gates

This document closes the gap between automated scratch-database tests, GitHub merge protection, and the owner-only production checks. It does not authorize an automatic production deployment.

## 1. GitHub merge protection (owner action)

The workflow can report a failed check, but only GitHub repository rules can prevent merging. After the workflow has run at least once on a pull request:

1. Open **Settings → Rules → Rulesets** (or **Settings → Branches → Branch protection rules**, depending on the repository configuration).
2. Create or edit the rule targeting `main`.
3. Enable **Require a pull request before merging**.
4. Enable **Require status checks to pass** and select both matrix checks produced by the `Database files check` workflow: `database-files (15)` and `database-files (16)`. If GitHub displays a slightly different exact check label, select the two entries corresponding to this workflow's PostgreSQL 15 and PostgreSQL 16 matrix jobs.
5. Enable **Require branches to be up to date before merging** (strict status checks).
6. Save the rule and verify it is active for `main`.

Why both matrix checks: a PR must pass on both supported PostgreSQL versions, not just one. Why branch freshness: it forces a PR to be re-tested against the latest `main`, preventing two individually passing PRs from independently introducing the same next migration number.

This is an owner configuration step. A file in the repository cannot switch on GitHub's enforcement setting.

## 2. Production preflight (owner-only, read-only checks)

Run these checks on the production server from the intended release checkout. Do not paste passwords, connection strings, `.env` contents, or secret values into a PR or chat. Do not run a migration as part of this preflight.

### A. Confirm the checkout and runtime targets

```bash
pwd
git status --short
git branch --show-current
git rev-parse HEAD

# Confirm the intended database and PostgreSQL server version without exposing credentials.
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d sb_app -Atc \
  "SELECT current_database(), current_setting('server_version'), current_setting('port');"
```

Expected database: `sb_app`. Production PostgreSQL major version is expected to be 15. The application backend port is `8001`; PostgreSQL listens on `5432`. If the query or runtime targets differ, stop and investigate before deployment.

### B. Check the live migration ledger and runner status

The baseline file `000_baseline_schema.sql` is only for an empty-database bootstrap. If it is absent from the live ledger while application tables or other user objects exist, the runner must refuse to apply it. Do not bypass that refusal by inserting a ledger row manually.

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d sb_app -c \
  "SELECT filename, sha256, applied_at FROM schema_migrations ORDER BY applied_at;"

bash backend/scripts/apply_schema.sh backend/schema --status
echo "runner_status_exit=$?"
```

The status command is read-only. A non-zero result, changed checksum, pending required file, missing ledger, or unexpected ledger shape means **stop**; do not merge/deploy on the assumption that the scratch tests prove production compatibility. Compare every file reported as applied with its live ledger checksum. Investigate ledger entries whose corresponding file is absent from the checkout.

### C. Confirm backup readiness

```bash
ls -ld /home/ec2-user/schema-backups
ls -lh /home/ec2-user/schema-backups/ | tail -n 10
```

Before an actual migration, the runner must create and validate a fresh custom-format backup itself. If backup creation or `pg_restore --list` validation fails, the runner must stop before applying any schema file. Do not treat an old backup as a substitute for the runner's fresh pre-change backup.

### D. Record the outcome

In the PR, record only non-secret facts: production database name, PostgreSQL major version, current commit, runner status and exit code, whether all required files/checksums match, and whether backup storage is available. If any check cannot be completed, mark it **NOT VERIFIED** and stop.

## 3. What CI does and does not prove

CI runs the complete schema set twice on disposable PostgreSQL 15 and 16 services, then runs the migration-runner test suite against separate throw-away databases. The runner tests include refusal to apply an unrecorded baseline over a populated database and least-privilege permission handling. CI also checks the exact four protected legacy filenames and prevents extra files from reusing `009` or `012`.

CI does **not** connect to production, inspect the live migration ledger, validate production data, create a production backup, or enable GitHub branch protection. Those remain explicit owner responsibilities.