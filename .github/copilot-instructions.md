# Super Bajaar — GitHub Copilot repository instructions

> **Current status (31 October 2026): standby only.** Copilot is not an active coding dependency while the user's Codespaces quota is exhausted. Do not start work or incur paid usage unless the owner confirms availability and explicitly assigns a task.

Read and follow:
1. `README.md`
2. `AGENTS.md`
3. `docs/AI_ENGINEERING_OPERATING_MODEL.md`
4. `docs/AI_TEAM_COLLABORATION.md`
5. `docs/GITHUB_COPILOT.md`
6. The task-specific canonical document identified by `AGENTS.md`.

## If explicitly re-enabled

- Work only on a specific GitHub issue with one accountable owner, one reviewer and exact reserved paths.
- Start from latest `main` on a focused feature branch. Never push directly to `main`.
- Inspect existing implementation/tests before editing. Preserve unrelated working code and architecture.
- Keep changes scoped; do not edit another contributor's reserved files.
- Add/update relevant tests and report exact commands/results. Never claim an unrun test passed.
- Update canonical documentation in the same PR.
- Required CI and owner review remain mandatory. Do not merge, bypass branch protection or deploy.
- Do not incur paid Copilot usage, Codespaces top-ups or external-service spend without explicit approval.

## Protected database and production rules

- Read `docs/DATABASE_CHANGE_RULES.md` and `CLAUDE.md` before database/schema/migration work.
- Do not edit, rename, delete, reformat or regenerate existing/applied migrations.
- Do not change migration numbering, `backend/schema_required.txt`, migration runner scripts or database CI policy outside the approved owner-controlled process.
- Claude remains the designated default SQL/schema/runner author under `CLAUDE.md`; Copilot is not authorised to take over.
- Do not apply production SQL/migrations, reset/delete data, change production roles/ownership or alter live records.
- Preserve backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, existing AWS EC2/Nginx/Gunicorn/Amplify/systemd arrangement unless the owner approves a verified change.
- Never expose credentials, tokens, passwords, private keys, connection strings, production `.env` values or private customer/payment data.

## Reporting

Report issue, owner, base SHA, files changed, behaviour changed, tests actually run and exact results, CI run/commit SHA, risks, limitations and deployment status. If access, quota, path ownership or approval is missing, stop and report the blocker.
