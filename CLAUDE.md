# Instructions for Claude

> **Role:** Designated default author/reviewer for SQL, schema migrations, migration-runner changes and database CI under the current project governance. The repository/database owner retains final authority.

## 1. Mandatory reading

Before any database, schema, table, data, migration, runner, backup, permission or deployment work:

1. Read `README.md` and `AGENTS.md`.
2. Read `docs/DATABASE_CHANGE_RULES.md` completely.
3. Read `docs/architecture.md` and `docs/DEVELOPMENT_WORKFLOW.md` when the task affects application architecture, APIs, tooling or deployment.
4. State that the required documents were read and identify the relevant sections.

## 2. Database authorship and approval

You are the default author of SQL migrations and changes to:

- `backend/scripts/apply_schema.sh`
- `backend/schema_required.txt`
- `backend/scripts/tests/test_apply_schema.sh`
- `.github/workflows/migration-check.yml`

The owner may explicitly authorize another agent to implement a specifically scoped database change. The exact authorization must be recorded in the PR. Without it, other agents must prepare a Database Change Request for the owner and designated database author.

The owner/database owner retains final authority over schema design, migration numbering, approval, production DB changes, table ownership/roles and release approval. No agent may infer approval from a request to investigate or document.

## 3. Required migration workflow

- Inspect the complete schema directory, protected historical files, current code dependencies and `backend/schema_required.txt`.
- Ask the owner to run the documented read-only production ledger/checksum preflight whenever live state affects the decision. Never infer production migration status from Git.
- Select a unique next number while respecting the exact grandfathered legacy filename pairs documented in the migration CI workflow.
- Create only the approved additive, idempotent migration file; never edit/rename/delete/reformat an applied migration.
- Update `schema_required.txt` when application code starts depending on the new schema file.
- Test the complete schema set twice on disposable PostgreSQL 15 and 16.
- If the runner changes, run `backend/scripts/tests/test_apply_schema.sh` and review backup, rollback, failure, alert and exit-code behaviour.
- Update database rules and the PR template where process behaviour changes.
- Open a feature-branch PR; never push directly to `main`.
- Production migration/deployment requires separate explicit owner approval and preflight.

## 4. Safety rules

- Never run destructive production SQL or reset production data.
- Never manually fabricate `schema_migrations` records to bypass a baseline or checksum guard.
- Never expose secrets, connection strings or environment values.
- Preserve backend port 8001, PostgreSQL 5432, database `sb_app`, API prefix `/api`, and existing AWS/service automation unless explicitly approved.
- A CI pass on disposable databases is not production certification.
- If a migration fails, report exact filename, observed error, exit code, backup status and safe next action. Do not improvise a live repair.

## 5. Documentation and evidence

Update the relevant canonical documents in the same PR. Record exact test commands, commit SHA, environment and observed result. Separate source verification, CI verification, production preflight, migration application, deployment and post-deployment verification.