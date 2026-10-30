## Change summary

## Agent task and handoff (when applicable)
- GitHub issue:
- Agent/provider and actual execution status:
- Provider run/task ID (if available):
- Starting branch / base commit:
- Allowed paths:
- Files changed:
- Handoff report and next owner:
- If no AI agent was used, state "Human-authored" or "Not applicable".


## Scope and acceptance criteria

## Documentation impact
- [ ] Read `README.md` and `AGENTS.md`.
- [ ] Read the task-specific canonical document(s).
- [ ] Updated relevant documentation in this PR.
- [ ] If no documentation change is needed, explain why below.
- [ ] Added a dated `IMPORTANT_UPDATES.md` entry for a major change.

## Architecture / API impact
- [ ] No architecture/API contract change.
- [ ] If changed, updated `docs/architecture.md` (routes, methods, auth, roles, request/response, data effects and errors).
- [ ] Verified UI → API → permission/business rule → PostgreSQL → response path where applicable.

## Database / schema impact
Does this PR touch SQL, schema, tables, data, migration runner, required-schema manifest, database permissions or a DB-dependent release? yes / no

If yes:
- [ ] Read `docs/DATABASE_CHANGE_RULES.md` and `CLAUDE.md`.
- [ ] Database author/owner approval is recorded.
- [ ] No existing/applied migration was edited, renamed, deleted or reformatted.
- [ ] New migration is additive, idempotent and correctly numbered under current legacy exceptions.
- [ ] `backend/schema_required.txt` updated when application code requires the new schema.
- [ ] Schema set passed twice on disposable PostgreSQL 15 and 16.
- [ ] Migration-runner tests passed if runner behaviour changed.
- [ ] Live production preflight was completed by the owner only if a release requires it; record non-secret evidence below.
- [ ] No production migration was run without separate explicit approval.

## Tooling / operations impact
- [ ] No tooling, GitHub workflow, deployment or infrastructure change.
- [ ] If changed, updated `docs/DEVELOPMENT_WORKFLOW.md` and/or relevant architecture/database guide.
- [ ] AWS was used only when runtime/hosting/infrastructure evidence justified it.
- [ ] No production service, timer, port, secret or deployment setting changed without approval.

## Tests actually run (include exact command/workflow and result)

## CI evidence
- Commit SHA:
- Backend tests:
- Frontend build(s):
- PostgreSQL 15/16:
- Other:

## Release status (do not conflate these)
- [ ] Source change complete
- [ ] CI verified on exact commit
- [ ] Reviewed / approved
- [ ] Merged
- [ ] Deployment separately approved
- [ ] Deployed (environment + commit):
- [ ] Post-deployment verified (evidence):

## Risks, blockers and exceptions

## Owner-only release gates
- [ ] Main branch protection requires PR review, required PostgreSQL matrix checks and up-to-date branches.
- [ ] If database release is needed, production preflight in `docs/DATABASE_CHANGE_RULES.md` was reviewed.
- [ ] Verified fresh backup is available before an approved production migration.

> Never claim a test, migration, deployment or production verification passed unless it was actually executed and observed.