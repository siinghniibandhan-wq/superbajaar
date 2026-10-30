## What this changes (plain words)

## Does this touch the database, tables, data, runner or deploy?  yes / no
If yes, I read `docs/DATABASE_CHANGE_RULES.md` and:
- [ ] SQL and runner changes were written by Claude, or another agent with the owner's explicit approval recorded in this PR
- [ ] No existing schema file was edited, renamed or deleted (or the exception is explained below)
- [ ] New file uses the next unused number and is repeatable (tested twice on Postgres 15 and 16)
- [ ] If code needs the new table/column, the file is added to `backend/schema_required.txt`
- [ ] Live checks were run by the owner, and the results are pasted below
- [ ] I have not claimed anything passed that I did not run

## Tests actually run (paste real output)

## Exceptions or risks

## Owner-only release gates (complete before merge/deploy)
- [ ] GitHub main-branch protection requires both PostgreSQL matrix checks and requires the branch to be up to date.
- [ ] Production preflight in `docs/RELEASE_GATES.md` was reviewed; live ledger/checksum results are recorded below (no secrets).
- [ ] A verified production backup is available before applying database changes.