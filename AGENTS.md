# Repository instructions for all contributors and AI agents

> **Read first.** These instructions apply to ChatGPT, Claude, Copilot, Codex, humans and any other contributor.

## 1. Mandatory reading before work

Every task starts by reading:

1. `README.md` — project overview, safety constraints, architecture summary and document index.
2. `AGENTS.md` — these shared contributor rules.
3. If the owner explicitly invokes Copilot inside an available Codespace, read `docs/GITHUB_COPILOT.md` and `.github/copilot-instructions.md`. Copilot is not an issue-assigned coding agent.
4. For multi-AI delegation, role boundaries, task batches or cross-agent handoffs, read `docs/AI_TEAM_COLLABORATION.md`, the canonical `docs/AI_ENGINEERING_OPERATING_MODEL.md`, and `docs/AI_AGENT_TASK_CHECK_COMMANDS.md`.
5. The task-specific canonical document in the matrix below.

| Work type | Mandatory detailed reading |
|---|---|
| Frontend page / UI / React feature | `docs/architecture.md`, `docs/DEVELOPMENT_WORKFLOW.md` |
| API endpoint / request / response / auth | `docs/architecture.md`, `docs/DEVELOPMENT_WORKFLOW.md` |
| Backend business logic | `docs/architecture.md` |
| Architecture / domain boundary / data flow | `docs/architecture.md`, `docs/PROJECT_PROGRESS_STRUCTURE.md` |
| Database / SQL / schema / data / migration | `docs/DATABASE_CHANGE_RULES.md`, `CLAUDE.md` |
| Security / access control | `docs/architecture.md`; database rules if data/schema is involved |
| AWS / deployment / hosting / runtime | `docs/DEVELOPMENT_WORKFLOW.md`; database rules if migration is involved |
| Audit / progress report | `docs/PROJECT_PROGRESS_STRUCTURE.md` and relevant technical document |
| Major project-wide change | `IMPORTANT_UPDATES.md` and relevant canonical document |

If a required document cannot be read, stop and tell the owner. Do not guess its contents.

## 2. Project operating model

- GitHub is the source of truth for code, review, PRs and CI.
- When the owner asks an AI agent to check assignments, follow `docs/AI_AGENT_TASK_CHECK_COMMANDS.md`: inspect only open issues routed to that agent, acknowledge before execution, and report no assignments when none match. This is user-invoked polling, not background automation.
- GitHub Codespaces is the preferred interactive development environment when available. If its budget or access is unavailable, do not incur paid usage without approval; use GitHub issues/PRs and Actions for supported repository workflows, and clearly mark terminal-only checks NOT RUN until an approved runner is available.
- Swagger / OpenAPI is the first diagnostic stop for API route, request/response, auth and status-code issues.
- AWS EC2 / Systems Manager Run Command are used when evidence indicates runtime, host, networking, environment or infrastructure issues.
- AWS Amplify is used for frontend build/hosting/deployment investigation.
- PostgreSQL production operations are owner-controlled.
- ChatGPT is the CTO/coordinator and owns architecture, task decomposition/allocation, integration, PR/evidence review and merge execution under repository approval rules. ChatGPT leads bounded application implementation. GitHub Copilot is an optional coding assistant inside Codespaces only when explicitly invoked and usage is available. Gemini is the independent read-only auditor and may implement only a separately assigned non-schema fix on reserved paths. Perplexity is the external research/source-verification specialist. Claude owns complex backend/data-integrity engineering and designated SQL/schema/migration/runner work under `CLAUDE.md`. Supporting tools (GitHub Actions, Codespaces, Context7, Firecrawl, TinyFish, Manufact, Linear, GitLab, 3Min API, AWS, Amplify and Swagger) are not interchangeable AI task owners. Read `docs/AI_AGENT_TASK_CHECK_COMMANDS.md` for exact role prompts and `docs/AI_ENGINEERING_OPERATING_MODEL.md` for the full responsibility/tool register. No AI replaces owner approval.

Follow the diagnostic order and tool boundaries in `docs/DEVELOPMENT_WORKFLOW.md`. Do not jump to AWS for ordinary source or API contract defects without evidence.

### 2A. AI role and access boundaries

The repository is public. Public read access is not authenticated write access, task dispatch or production permission.

- **ChatGPT:** CTO/coordinator; connected GitHub tools may read/write supported GitHub resources. Verify each operation. Use feature branches and PRs; owner policy controls merge and release.
- **GitHub Copilot:** primary bounded React/Vite and non-schema FastAPI implementation agent. It may write only when a supported Copilot coding-agent session is actually started for its assigned issue.
- **Google Gemini:** public-repository read-only auditor by default. No repository write permission is assumed. A separate implementation requires a new issue and reserved paths.
- **Perplexity:** public-repository context plus external research; research-only, no repository writes.
- **Claude:** public-repository read access and patch delivery; direct GitHub write access is not assumed. Claude is the designated complex backend/database and SQL/schema/migration/runner specialist under `CLAUDE.md`.
- **GitHub labels, @mentions and issue creation are routing/coordination metadata, not proof of delivery, acknowledgement or execution.**
- No public-repository access grants production data, credentials, private resources, AWS, database operations or deployment.

## 3. GitHub and PR rules

- Start from the latest `main`; create a focused feature branch.
- Never push directly to `main`.
- Do not overwrite or revert unrelated working code.
- Every PR must state purpose, scope, owner, acceptance criteria, tests actually run, documentation impact and schema/deployment impact.
- Review the complete diff and required CI checks on the exact commit.
- Keep the branch current with `main`.
- The owner controls merge and production release approval.
- Normal portfolio ceiling: 15 open PRs. Resolution target: 5 calendar days; review/escalation by Day 7; target resolution by Day 10 through merge or reasoned closure. These are team operating targets, not automatic GitHub enforcement.
- Never merge unsafe work or close valid work only to meet the PR count/age target. Document blocker, owner and next review date; urgent security/production work may exceed the cap with owner visibility.
- Merged does not mean deployed. Deployment requires separate authorization.

## 4. Documentation is part of the change

Update the canonical document in the same PR whenever implementation changes its subject:

- API path, method, request/response, authentication or role policy → `docs/architecture.md`.
- UI/page, service, integration, domain boundary or data flow → `docs/architecture.md`.
- Schema, migration, runner, required migration list, database permissions or release procedure → `docs/DATABASE_CHANGE_RULES.md` and relevant schema manifest/runner tests.
- Tooling, diagnostic sequence, GitHub flow or operational process → `docs/DEVELOPMENT_WORKFLOW.md`.
- Project-wide overview, current critical status or top-level stack → `README.md`.
- Major decision, merged feature or release milestone → dated entry in `IMPORTANT_UPDATES.md`.
- Progress/audit reporting framework → `docs/PROJECT_PROGRESS_STRUCTURE.md`.
- PR acceptance rules → `.github/pull_request_template.md`.

Every PR must either update the affected canonical document(s) or state why no documentation change is required. Avoid duplicate sources of truth. README is the index/overview, not a duplicate of every runbook.

## 5. Database governance — stop and read first

Before any task involving tables, data, SQL, migrations, backup, database permissions, customers, orders, payments, loyalty or deployment with schema impact:

1. Read `docs/DATABASE_CHANGE_RULES.md` completely.
2. Read the database-specific instructions in `CLAUDE.md`.
3. State in the work plan that both documents were read.
4. Identify whether the task truly requires a schema change.
5. If another agent is not explicitly authorized to author SQL/runner changes, prepare a Database Change Request for the owner and designated database author.

**Repository owner and database owner retain final authority** over schema design, migration numbering, approval, production DB changes and release approval. Reviewers do not replace that authority.

Protected assets include:

- `backend/schema/`
- `backend/schema_required.txt`
- `backend/scripts/apply_schema.sh`
- migration-runner tests and database CI workflow.

Never edit, rename, delete, replace, regenerate or reformat an existing/applied migration. Never infer live database state from Git. Use only the approved additive, idempotent, uniquely numbered migration process. The exact legacy numbering exceptions and current protected files are defined in the database rules and migration CI workflow; inspect them before selecting a number.

Never run destructive production SQL, reset production, manually fabricate migration ledger entries, or change table ownership/roles without explicit owner approval and a reviewed plan.

## 6. Runtime and production safety

Preserve the established targets unless the owner explicitly approves a verified change:

- Backend: `127.0.0.1:8001`.
- PostgreSQL: `5432`; production database: `sb_app`.
- Public API prefix: `/api`.
- Existing AWS EC2 + Nginx + Gunicorn backend.
- Existing AWS Amplify frontend.
- Existing systemd service/timer and synchronization mechanism.

Never expose credentials, access tokens, connection strings or `.env` values. Do not deploy or run production migrations as an automatic side effect of coding, documentation or CI.

## 7. Verification and reporting

- Record exact command/workflow, commit SHA, environment and observed result.
- Distinguish source review, local test, CI, staging and production verification.
- Do not claim tests/builds/routes/database operations/deployment passed unless actually executed.
- A green CI run does not certify production database state, backups, live deployment or end-to-end business workflows.
- Use the statuses and report format in `docs/PROJECT_PROGRESS_STRUCTURE.md`.
- Put latest verified update, critical blocker and latest audit finding first. Do not label unverified assumptions as findings.

## 8. If instructions conflict

Stop. Explain the conflict, affected files/data/services and safe options. Ask the owner before proceeding. Do not improvise a destructive or broad refactor.
