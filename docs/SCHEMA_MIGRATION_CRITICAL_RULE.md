# Critical rule: PostgreSQL migration filenames are immutable

> **STOP — DO NOT RENAME, EDIT, MOVE OR DELETE AN EXISTING MIGRATION FILE.**

Every SQL file in `backend/schema/` is a versioned migration. Its filename, including its three-digit number and descriptive suffix, is part of the migration identity recorded by the production migration ledger.

For example, once `036_example_change.sql` has been applied, do not rename it to `037_example_change.sql`, change its spelling, move it, delete it, or edit its SQL contents. A filename change is not a harmless cleanup: it can make the repository disagree with the production ledger, cause a required-file check to fail, or make a database appear to be missing a migration.

## Required procedure

1. **Treat every existing migration filename and file content as immutable.** This applies especially to every migration already applied in any shared environment.
2. If a schema change or correction is needed, create a **new** migration with the next unused consecutive number after checking the complete current `backend/schema/` directory and target branch.
3. Never reuse a number, renumber an old migration, or fill historical numbering gaps.
4. Do not edit `schema_migrations` or manually change recorded checksums to make a renamed or edited file appear valid.
5. If an already-applied file was accidentally changed or renamed in Git, restore the exact original filename and content from the commit whose SHA-256 matches the recorded migration checksum. Submit that restoration through a reviewed PR. Do not rewrite the production ledger.
6. Do not apply a new migration to production merely because it merged. Production application requires the separately approved operational procedure.

## Pull request gate

The `.github/workflows/schema-governance.yml` check compares the PR with its base branch. It fails if an existing schema file is modified, renamed or deleted; if a new migration filename is invalid; if a number is duplicated; or if newly added migration numbers are not consecutive after the current maximum.

This CI check is an additional guardrail. It does not authorize production changes and does not replace migration review, backup verification or explicit production approval.

**If in doubt: leave the existing file untouched and ask for a new migration number.**
