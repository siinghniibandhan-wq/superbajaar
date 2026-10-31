# Super Bajaar — GitHub Copilot repository instructions

> **Status: standby only (31 October 2026).** Codespaces usage is exhausted. Do not start work or incur paid usage unless the owner confirms availability and explicitly assigns a task.

Read `README.md`, `AGENTS.md`, `docs/AI_ENGINEERING_OPERATING_MODEL.md`, `docs/AI_TEAM_COLLABORATION.md`, `docs/GITHUB_COPILOT.md` and task-specific instructions.

If explicitly re-enabled:
- Work only on a bounded issue with one owner, one reviewer and exact reserved paths.
- Start from latest `main` on a feature branch. Never push directly to `main`.
- Inspect existing implementation/tests; preserve unrelated working code.
- Do not edit another contributor's reserved paths.
- Add/update relevant tests and report exact commands/results. Never claim an unrun test passed.
- Update canonical documentation in the same PR.
- Required CI and owner review remain mandatory. Do not merge, bypass branch protection or deploy.
- Do not incur paid Copilot usage, Codespaces top-ups or external-service spend without explicit approval.

## Protected database and production rules

Read `docs/DATABASE_CHANGE_RULES.md` and `CLAUDE.md` before database work. Claude remains the designated SQL/schema/migration/runner specialist. Do not edit, rename, delete, reformat or regenerate historical/applied migrations. Do not change migration numbering, `backend/schema_required.txt`, `backend/scripts/apply_schema.sh` or migration CI outside the approved owner-controlled process. Never apply production SQL/migrations, reset/delete data, change production roles or alter live records.

Preserve backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, and current AWS EC2/Nginx/Gunicorn/Amplify/systemd arrangement unless the owner approves a verified change. Google Cloud is unavailable and is not an active deployment target.

Never expose credentials, tokens, private keys, production `.env` values or customer/payment data.

## Reporting
Report issue, owner, base SHA, files changed, behaviour changed, tests actually run and exact results, CI run/commit SHA, risks and deployment status. If quota, access, path ownership or approval is missing, stop and report the blocker.
