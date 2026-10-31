# Super Bajaar — AI Engineering Operating Model

> **Final proposed model — 31 October 2026.** ChatGPT leads. Gemini and Perplexity are equal engineering partners. Claude owns database specialism. Copilot is standby. Google Cloud is excluded because access is unavailable.

## 1. Command and accountability
- **Project owner:** final authority for priorities, access, paid usage, secrets, protected production/database changes, merge and release approval.
- **ChatGPT — CTO / Team Lead:** architecture, strategy, task decomposition, allocation, GitHub coordination, integration, review, documentation governance, QA evidence and release readiness.
- One task has one accountable owner, one reviewer and one reserved path set. No simultaneous edits to the same files.
- GitHub is the shared source of truth: issues for scope/decisions, branches and PRs for code/review, Actions for CI evidence, canonical docs for policy.
- Separate AI accounts do not automatically communicate. Use GitHub issue/PR handoffs. Never claim an agent was dispatched or completed work without evidence.
- No direct push to `main`, self-merge, branch-protection bypass, unapproved spend, production mutation or deployment.

## 2. Final team responsibility matrix

| Member | Role | Responsibilities | Boundaries |
|---|---|---|---|
| **ChatGPT** | **CTO / Team Lead / Integration Owner** | Architecture, planning, allocation, GitHub coordination, authorised code/docs work, integration, review, test strategy and release readiness. | Does not impersonate agents or claim unrun tests. No unapproved paid/production/merge/deploy action. |
| **Gemini** | **Equal Engineering Partner A** | Assigned frontend/backend implementation, debugging, refactoring, testing, module audits, security/performance review and independent PR review. | Confirm actual access. One reserved path set per task. No schema/migration ownership or production actions. |
| **Perplexity** | **Equal Engineering Partner B** | Assigned frontend/backend implementation, debugging, refactoring, testing, research, source verification, code review and independent audits. | May edit assigned code using owner-granted access but **must not commit or push**. Return full diff/patch, changed paths and test evidence to ChatGPT. No schema/migration or production work unless separately approved. |
| **Claude** | **Database & Complex Backend Specialist** | SQL, schema, additive migrations, migration runner, database CI, data integrity, transaction/concurrency and complex backend work under `CLAUDE.md` and database rules. | Never alter historical/applied migrations. No production SQL, migration execution or release without explicit owner approval and preflight. |
| **GitHub Copilot** | **Standby coding assistant** | Optional bounded coding when Codespaces is available and owner reactivates it. | Codespaces quota is exhausted. Not an active dependency. No paid top-up without approval. |
| **GitHub Actions** | CI executor | Builds, tests, security and schema/policy checks. | Automation, not an AI agent; CI pass is not production verification. |
| **GitHub** | Shared project system | Issues, branches, commits, PRs, reviews, permissions and CI records. | Not an AI agent; labels do not prove dispatch or completion. |

### Equal workload policy — Gemini and Perplexity
- Split eligible non-schema work into comparable, independently deliverable tasks.
- Rotate first implementation ownership across batches; neither is permanently only coder or reviewer.
- Each receives a balanced mix of implementation and independent review over time.
- Use different files/modules or sequential batches. Never edit the same path set concurrently.
- ChatGPT tracks assignment and completion evidence in GitHub.
- Perplexity's no-commit/no-push restriction remains; ChatGPT integrates accepted changes using authorised GitHub tools.

## 3. Supporting tools and access reality

| Tool | Use / status |
|---|---|
| GitHub / Actions | Active source control, task tracking, PR and deterministic CI |
| Figma | Approved UI/UX design and design-to-code when connected |
| Context7 | Current framework/library documentation |
| Firecrawl / TinyFish / web | External research and authorised browser tasks |
| GitBook | Documentation site only when connected and in scope |
| Linear | Optional planning mirror; GitHub remains canonical |
| GitLab | Secondary repo/CI only when required |
| Manufact | MCP server/deployment management; not default app deployer |
| 3Min API | Approved API experiments; not production FastAPI by default |
| OpenAI Platform | OpenAI API administration; explicit request only, may be billable |
| Files / Library | Project-document retrieval |
| Plugin Management | Discover/manage integrations; owner action required to connect |
| Automations | Reminders/monitoring, not AI-agent dispatch |
| **Google Cloud** | **Unavailable; excluded from active team. No GCP access, assignment, deployment or resource creation assumed.** |
| **Codespaces** | Usage exhausted; no paid top-up without owner approval |

A subscription or listed plugin does not prove a connector is active in this chat. Verify each capability before use.

## 4. Work allocation

| Workstream | Owner | Support / reviewer |
|---|---|---|
| Product priorities and acceptance | Project owner | ChatGPT |
| Architecture and cross-module design | ChatGPT | Gemini + Perplexity; Claude for DB implications |
| Task decomposition, issue allocation and path reservation | ChatGPT | Relevant agent |
| Non-schema implementation batch A | Gemini or Perplexity (rotate) | Other partner read-only; ChatGPT integrates |
| Non-schema implementation batch B | Perplexity or Gemini (rotate) | Other partner read-only; ChatGPT integrates |
| Independent module/PR audits | Gemini and Perplexity (balanced rotation) | ChatGPT consolidates |
| Complex backend, data integrity and SQL/schema/migration/runner | Claude | ChatGPT coordinates; Gemini/Perplexity read-only challenge |
| External facts, vendor/API and Indian compliance research | Perplexity; Gemini may cross-check | ChatGPT validates |
| Builds/tests | GitHub Actions or approved terminal | ChatGPT reviews exact run/commit |
| Integration, final audit and release readiness | ChatGPT | Gemini/Perplexity; Claude for DB changes |
| Merge and production release | Owner approval required | ChatGPT acts only within explicit authorisation |

## 5. Standard workflow
1. ChatGPT inspects latest `main`, open issues/PRs, changed files and active path reservations.
2. Define objective, impact, owner, reviewer, base SHA, allowed/protected paths, dependencies, acceptance criteria, tests and approval gates.
3. Classify non-schema vs schema/database; flag security, infrastructure, paid and production impact separately.
4. Assign one owner. Balance Gemini and Perplexity; Claude owns database work; Copilot stays standby.
5. Assignee confirms identity, access, scope and acceptance in GitHub before editing.
6. Implement on a feature branch from latest `main`; keep batches small. Perplexity returns a diff without commit/push.
7. A different agent reviews read-only. Rotate Gemini/Perplexity review duties; Claude reviews DB implications.
8. ChatGPT checks full diff, API/business rules, permissions, security, docs, schema impact and regressions.
9. Run frontend build and backend tests separately. Prefer Actions while Codespaces is unavailable. Mark unavailable commands NOT RUN.
10. PR records issue, files, exact commit, tests and risks. Owner approves merge. Deployment is separate and needs explicit approval plus post-deploy verification.

### Required task brief
```text
Issue:
Task owner:
Reviewer:
Task type: implementation / audit / research / QA / documentation
Base branch + SHA:
Allowed paths:
Protected paths:
Objective and acceptance criteria:
Dependencies:
Tests / commands:
Files inspected / changed:
Evidence: PASS / FAIL / NOT VERIFIED
Risks / blockers:
Next owner:
Schema / infrastructure / paid / production impact:
Approval required:
```

## 6. Repository, database and production safeguards
- Feature branches only; never push directly to `main`. Preserve unrelated working code.
- Read `docs/DATABASE_CHANGE_RULES.md` and `CLAUDE.md` before database work. Claude is default SQL/schema/migration/runner author.
- Never edit, rename, delete or reformat historical/applied migrations. Do not touch `backend/schema/000_baseline_schema.sql` or `backend/schema/009_loyalty_programme.sql`.
- Follow unique numbering, one-new-file-per-change, additive/idempotent SQL and existing CI rules. Do not alter `backend/schema_required.txt`, `backend/scripts/apply_schema.sh` or migration CI outside approved scope.
- No production data writes, destructive SQL, production migration, secrets/roles change, infrastructure change or deployment without explicit owner approval and preflight.
- Preserve current setup unless owner approves a verified change: backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, AWS EC2 + Nginx + Gunicorn backend, Amplify frontend and existing systemd service/timer.
- No Google Cloud actions. Never expose credentials, tokens, private keys, production `.env`, customer or payment data.

## 7. Diagnostics and verification
1. GitHub issue/PR/commit/CI state.
2. Swagger/OpenAPI first for route, request/response, auth and status defects.
3. Trace UI → API client → FastAPI route → service/business rules → SQL/data model.
4. Use approved terminal or GitHub Actions; Codespaces is unavailable currently.
5. AWS only when evidence points to runtime/host/network/environment/log/infrastructure; Amplify for frontend hosting/build.
6. Production DB state only through owner-approved read-only preflight.
7. Verify exact commit, required CI, targeted tests and relevant user journey.
8. Deployment is a separate owner-approved step.

## 8. Status and truthfulness
Use `READY`, `ACKNOWLEDGED`, `IN PROGRESS`, `BLOCKED`, `REVIEW`, `COMPLETE`. Reports include actual commands, results, commit/CI evidence, changed paths and risks. Use PASS / FAIL / NOT VERIFIED accurately. Stop on missing access, overlapping paths, stale base SHA, protected assets, unclear approval or unapproved spend. GitHub labels/@mentions do not wake external AIs; no unattended dispatch is assumed.

## 9. Documentation governance
Keep `docs/AI_TEAM_COLLABORATION.md`, `docs/AI_AGENT_TASK_CHECK_COMMANDS.md`, `AGENTS.md`, `.github/copilot-instructions.md` and `README.md` consistent with this canonical model.
