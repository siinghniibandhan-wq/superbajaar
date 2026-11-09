# Repository instructions for all contributors and AI agents

> Read first. These instructions apply to ChatGPT, Claude, Copilot, Codex, humans and every other contributor.

## 1. Mandatory reading

Every task starts by reading:
1. README.md — project overview, safety constraints, architecture and document index.
2. AGENTS.md — shared contributor rules.
3. For Copilot work, docs/GITHUB_COPILOT.md and .github/copilot-instructions.md.
4. For multi-agent delegation, docs/AI_TEAM_COLLABORATION.md, docs/AI_ENGINEERING_OPERATING_MODEL.md and docs/AI_AGENT_TASK_CHECK_COMMANDS.md.
5. The task-specific canonical document below.

| Work type | Required reading |
|---|---|
| Frontend / React / UI | docs/architecture.md, docs/DEVELOPMENT_WORKFLOW.md |
| API / request / response / auth | docs/architecture.md, docs/DEVELOPMENT_WORKFLOW.md |
| Backend business logic | docs/architecture.md |
| Architecture / domain / data flow | docs/architecture.md, docs/PROJECT_PROGRESS_STRUCTURE.md |
| Database / SQL / schema / migration | docs/DATABASE_CHANGE_RULES.md, CLAUDE.md |
| Security / access control | docs/architecture.md; database rules when data/schema is involved |
| AWS / deployment / runtime | docs/DEVELOPMENT_WORKFLOW.md; database rules when migration is involved |
| Audit / progress report | docs/PROJECT_PROGRESS_STRUCTURE.md and relevant technical document |
| Major project-wide change | IMPORTANT_UPDATES.md and relevant canonical document |

If a required document is unavailable, stop and report the exact missing document. Do not guess.

## 2. Project operating model

- GitHub is the source of truth for code, review and CI.
- Agent assignment polling is user-invoked, not background automation. Follow docs/AI_AGENT_TASK_CHECK_COMMANDS.md; inspect only open issues routed to the relevant agent, acknowledge before execution and report when none match.
- GitHub Codespaces is preferred when available. Do not incur paid usage without approval. If no approved runner is available, mark terminal-only checks NOT RUN.
- Swagger / OpenAPI is the first diagnostic stop for API route, contract, auth and status-code issues.
- Use AWS EC2 / Systems Manager only when evidence points to runtime, host, networking or infrastructure. Use Amplify for frontend hosting/build investigation.
- PostgreSQL production operations are owner-controlled.
- ChatGPT acts as CTO/team lead and lead technical reviewer: architecture, task decomposition, GitHub coordination, integration, evidence review and release readiness. Perplexity may independently review or implement explicitly assigned work but must not commit or push. The repository owner retains final approval and merge authority.
- Copilot is an optional secondary coding assistant, not a PR reviewer, approver, required reviewer or release dependency.
- Claude is the designated complex backend and SQL/schema/migration/runner specialist under CLAUDE.md. Gemini is outside the active review/approval chain unless the owner changes that policy.
- Google Cloud is unavailable and excluded from active work. Supporting tools are not interchangeable AI task owners.

Follow docs/DEVELOPMENT_WORKFLOW.md. Do not jump to AWS for ordinary source/API defects without evidence.

## 3. GitHub workflow and owner direction

- Start from the latest main and inspect the exact current tree and commit.
- Never overwrite or revert unrelated working code.
- Review the complete diff and verify the exact commit.
- A normal change uses a focused feature branch and PR. However, the repository owner may explicitly direct a specific task to be committed directly to main; that explicit instruction is the controlling exception for that task. Do not create a branch or PR when the owner has explicitly instructed direct-main work.
- A PR, when used, must state purpose, scope, owner, acceptance criteria, tests actually run, documentation impact and schema/deployment impact.
- The owner controls merge and production release approval. Merged does not mean deployed.
- Portfolio target: normally no more than 15 open PRs; 5 calendar-day resolution target, review/escalation by Day 7 and target resolution by Day 10. These are operating targets, not automatic enforcement.
- Never merge unsafe work or close valid work merely to meet age/count targets. Preserve dependencies and unique work. Do not delete branches without separate approval.

## 4. Documentation requirements

Update canonical documentation with the implementation it describes:
- API path/method/request/response/auth/role policy and UI/service/domain/data flow → docs/architecture.md.
- Schema/migration/runner/required migration list/database permissions/release procedure → docs/DATABASE_CHANGE_RULES.md and relevant manifest/runner tests.
- Tooling, diagnostics, GitHub flow and operating process → docs/DEVELOPMENT_WORKFLOW.md.
- Project overview, critical status and stack → README.md.
- Major decisions, features and milestones → dated entry in IMPORTANT_UPDATES.md.
- Progress/audit framework → docs/PROJECT_PROGRESS_STRUCTURE.md.
- PR acceptance rules → .github/pull_request_template.md.

Avoid duplicate sources of truth. README is an index/overview, not a duplicate of every runbook.

## 5. Database governance — stop and read first

Before work involving tables, data, SQL, migrations, backups, database permissions, customers, orders, payments, loyalty or deployment with schema impact:
1. Read docs/DATABASE_CHANGE_RULES.md completely.
2. Read the database-specific instructions in CLAUDE.md.
3. Identify whether a schema change is genuinely required.
4. State the database review/approval boundary in the work plan.
5. Unless explicitly authorized, prepare a Database Change Request for the owner and designated database author.

The repository/database owner retains final authority over schema design, migration numbering, production DB changes and release approval.

Protected assets include backend/schema/, backend/schema_required.txt, backend/scripts/apply_schema.sh, migration-runner tests and database CI. Never edit, rename, delete, replace or reformat an existing/applied migration. Never infer live database state from Git. Use only the approved additive, idempotent, uniquely numbered migration process and inspect the current protected-file rules before selecting a number.

Never run destructive production SQL, reset production, fabricate migration-ledger entries or change table ownership/roles without explicit owner approval and a reviewed plan.

## 6. Runtime and production safety

Preserve established targets unless the owner explicitly approves a verified change:
- Backend: 127.0.0.1:8001.
- PostgreSQL: 5432; production database: sb_app.
- Public API prefix: /api.
- Existing AWS EC2 + Nginx + Gunicorn backend.
- Existing AWS Amplify frontend.
- Existing systemd service/timer and synchronization mechanism.

Never expose credentials, tokens, connection strings or .env values. Coding, documentation and CI must not automatically deploy or run production migrations.

## 7. Verification and reporting

- Record exact command/workflow, commit SHA, environment and observed result.
- Separate source review, local tests, CI, staging and production verification.
- Never claim tests, builds, routes, database operations or deployment passed unless actually executed.
- CI does not certify production database state, backups, live deployment or end-to-end workflows.
- Use docs/PROJECT_PROGRESS_STRUCTURE.md. Put latest verified update, critical blocker and latest audit finding first. Do not label assumptions as findings.

## 8. Conflicts and coordination

If instructions conflict, stop and explain the conflict, affected files/data/services and safe options. Do not improvise a destructive or broad refactor.

For project-wide audits, release planning, infrastructure work or PR portfolio cleanup, first read docs/CURRENT_OPERATING_BASELINE_2026-11-01.md. Treat dated evidence as a snapshot and reverify when later changes or concrete discrepancies require it.

The CTO coordinator maintains one consolidated work register across coding, audit, fixes, verification and release. Each task states owner, scope, files/layer, dependencies, prohibited actions, acceptance criteria and evidence. Avoid overlapping assignments. Independent reviewers report findings; an implementation author's test claims are not independent approval.

### PR portfolio disposition
- Inventory open PRs and classify KEEP / REVIEW / CLOSE-CANDIDATE.
- Compare patches and changed files against main and other PRs; titles or age do not prove duplication.
- Preserve unique unfinished work, dependencies and security fixes.
- Close only merged, fully superseded, abandoned with no unique value, or explicitly owner-directed work.
- Record closure reason and replacement reference. Do not delete branches without separate approval.

### Documentation synchronization
When runtime, tooling, agent roles, release gates, scope or procedures change, update canonical documents, README index/status and IMPORTANT_UPDATES.md. Update agent instructions, templates and workflows when their rules actually change. Repository docs do not change external AI account prompts or provider settings.

## 9. Automatic production schema runner

Before creating, editing, reviewing or referencing SQL/schema dependencies, read Database Change Rules section 16. The owner reports an sb-schema.timer that runs every five minutes and may apply a new SQL file before matching application code is deployed. The historical duplicate prefixes 009 and 012 are exceptions only; verify the current manifest, migrations, active PRs and live ledger before choosing any new number.

Never edit applied SQL, hand-edit schema_migrations, alter schema_required.txt outside the database-owner process, or change apply_schema.sh / its systemd timer or service without explicit owner approval. Keep migrations additive, idempotent, transactional and explicitly granted to superbajaar_user. Preserve compatibility before and after automatic application. Documentation-only work must not run migration apply/status/retry commands unless specifically requested.
