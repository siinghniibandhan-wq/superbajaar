# Instructions for Claude

> Role: Designated default author/reviewer for SQL, schema migrations, migration-runner changes and database CI under project governance. The repository/database owner retains final authority.

## 1. Mandatory reading

Before database, schema, table, data, migration, runner, backup, permission or deployment work:
1. Read README.md and AGENTS.md.
2. Read docs/DATABASE_CHANGE_RULES.md completely.
3. Read docs/architecture.md and docs/DEVELOPMENT_WORKFLOW.md when architecture, APIs, tooling or deployment is affected.
4. State which required documents and sections were read.

## 2. Database authorship and approval

Default database-authoring scope:
- backend/scripts/apply_schema.sh
- backend/schema_required.txt
- backend/scripts/tests/test_apply_schema.sh
- .github/workflows/migration-check.yml
- SQL migration files explicitly approved for the task.

The owner may explicitly authorize another agent to implement a specifically scoped database change; record that authorization in the work record/PR. Otherwise, prepare a Database Change Request for the owner and designated database author.

The owner/database owner retains final authority over schema design, numbering, approval, production DB changes, table ownership/roles and release approval. Investigation or documentation requests are not approval.

## 3. Required migration workflow

- Inspect the complete schema directory, protected historical files, current code dependencies and backend/schema_required.txt.
- When live state affects a decision, ask the owner to run the documented read-only production ledger/checksum preflight. Never infer production migration status from Git.
- Select a unique next number while respecting only the exact grandfathered legacy filename pairs in the migration CI workflow.
- Create only the approved additive, idempotent migration. Never edit, rename, delete or reformat an applied migration.
- Update schema_required.txt when application code starts depending on a new schema file.
- Test the complete schema set twice on disposable PostgreSQL 15 and 16.
- If the runner changes, run backend/scripts/tests/test_apply_schema.sh and review backup, rollback, failure, alert and exit-code behaviour.
- Update database rules and the PR template when process behaviour changes.
- Use a feature-branch PR by default. If the owner explicitly directs a specific task to be committed directly to main, follow that instruction only for that task; do not create a branch or PR.
- Production migration/deployment requires separate explicit owner approval and preflight.

## 4. Safety rules

- Never run destructive production SQL or reset production data.
- Never fabricate schema_migrations records to bypass a baseline/checksum guard.
- Never expose secrets, connection strings or environment values.
- Preserve backend port 8001, PostgreSQL 5432, database sb_app, API prefix /api and existing AWS/service automation unless explicitly approved.
- Disposable-database CI is not production certification.
- If a migration fails, report exact filename, observed error, exit code, backup status and safe next action. Do not improvise a live repair.

## 5. Documentation and evidence

Update relevant canonical documents with the change. Record exact test commands, commit SHA, environment and observed result. Separate source verification, CI, production preflight, migration application, deployment and post-deployment verification.

## Production automatic schema runner — mandatory

The owner reports that production has an sb-schema.timer running backend/scripts/apply_schema.sh every five minutes. It may apply a new migration before matching code deploys and does not restart the application. Read Database Change Rules section 16 before database work.

Historical sequencing notes in older handovers may be stale. Re-check current main, active PR heads, protected migration files and the live ledger before assigning any number. Only the exact existing 009 and 012 duplicate pairs are grandfathered. Never edit/rename/delete/reformat applied migrations or hand-edit the migration ledger. Do not modify the runner, timer or service without explicit owner approval.

Migrations must be additive, idempotent, run within the runner's per-file transaction (no BEGIN/COMMIT or non-transactional statements), and explicitly grant required table/sequence privileges to superbajaar_user. Test on sb_app_restore_test and disposable PostgreSQL 15/16 CI. Preserve compatibility both before and after automatic application. Do not run production commands or migrations without explicit authorization.
