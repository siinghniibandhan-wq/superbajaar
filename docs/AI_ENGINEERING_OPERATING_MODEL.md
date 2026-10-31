# Super Bajaar — AI Engineering Operating Model

> **Status: Proposed final operating model — 31 October 2026.** This document supersedes earlier role allocations that treated Copilot as the primary coder or Perplexity as research-only. It records the tools and access actually available today; it does not claim unattended agent-to-agent integrations.

## 1. Command, accountability and principles

- **Project owner:** final authority for product priorities, access, paid usage, secrets, protected production/database changes, merge and release approval.
- **ChatGPT — CTO and team lead:** owns architecture, planning, task decomposition, allocation, GitHub coordination, integration, technical review, documentation governance, QA evidence review and release readiness. ChatGPT is the single coordination point and does not claim another provider's work.
- **One task = one accountable owner. One active writer per path set.** Reserve exact paths and base SHA in GitHub before implementation. Reviewers remain read-only unless a separate issue assigns implementation.
- **GitHub is the shared project record:** Issues contain scope and decisions; branches/PRs contain code and review; Actions contain CI evidence; canonical Markdown docs contain the current operating rules.
- Separate Gemini, Claude and Perplexity chats do not automatically communicate with ChatGPT or each other. Use GitHub issue/PR comments and concise handoff reports to keep everyone in the loop.
- No direct push to `main`, no self-merge, no branch-protection bypass, no production mutation or deployment without the owner's explicit approval.
- No unapproved paid usage, new cloud service, API spend, Codespaces top-up or subscription change.

## 2. Current team and responsibility matrix

| Member / platform | Role in Super Bajaar | Execution boundaries |
|---|---|---|
| **ChatGPT** | **CTO / Team Lead / Integration Owner.** Architecture, technical decisions, task planning, GitHub issue/PR coordination, code and documentation work through available authorised tools, review, integration, test strategy and final audit. | Cannot directly operate another AI account unless a real connector/session is available. Must distinguish its own edits from external-agent work. No unapproved production, paid, merge or deployment actions. |
| **Gemini** | **Independent technical analyst and audit partner.** Second-opinion architecture, code-flow analysis, module audits, debugging hypotheses, test-gap/security/performance review and review of proposed fixes. | Implementation only when a distinct task is assigned, its actual repository/environment access is verified, and paths are reserved. Do not assume Gemini is connected to this ChatGPT session. |
| **Claude** | **Deep engineering and database specialist.** Difficult backend/data-integrity/concurrency/performance issues; SQL/schema design, additive migrations, migration runner and database CI under `CLAUDE.md` and database rules. Also provides independent code reasoning for high-risk changes. | No edits to historical/applied migrations; no production SQL or release without owner approval and preflight. Direct repository access must be verified; otherwise return a reviewed patch/design for ChatGPT to apply. |
| **Perplexity** | **Research, verification and audit partner.** Official documentation, vendor/API capability checks, security advisories, pricing/plan checks, technical comparisons and Indian e-commerce/GST/compliance research. May also make specifically assigned repository code edits using the access the owner has granted. | Per owner instruction, Perplexity may edit assigned code but **must not commit or push**. It must return changed paths, diff/patch and test evidence. ChatGPT reviews and owns integration/commit/PR. No schema/migration or production work unless separately authorised. No assumption of a direct Perplexity connector in this ChatGPT session. |
| **Google Cloud (GCP)** | **Infrastructure/cloud workstream.** Keep GCP in the architecture and deployment loop for cloud design, compute/storage/networking, IAM, monitoring, cost controls and migration options when a task calls for it. | GCP is a cloud platform, not an AI coding agent. No direct GCP console/API access is assumed here. Existing production hosting remains AWS EC2 + Nginx/Gunicorn + Amplify unless the owner approves a researched migration plan. No new GCP resources or charges without approval. |
| **GitHub Copilot** | **Standby coding assistant, Codespaces-dependent only.** May be reconsidered when Codespaces usage becomes available and the owner chooses to use it. | Current Codespaces usage limit is exhausted. Copilot is not an active dependency or primary coder now. Do not wait for it, assign critical work to it, top up, or incur charges without approval. |
| **GitHub Actions** | Deterministic build, test, security, schema-policy and CI execution. | Automation, not an AI agent. Green CI is not production verification. |
| **GitHub** | Canonical code, issue, branch, PR, review, CI and permission system. | Not an AI agent. Labels do not prove dispatch, acknowledgement or completion. |

### ChatGPT-connected supporting tools and plugins

Use these only when relevant to the task and when the actual connection/permission is available. They support the team; they do not replace accountable owners.

| Tool / plugin | Approved use |
|---|---|
| GitHub | Repository inspection, branches, issues, PRs, code review and CI evidence |
| Figma | Approved UI/UX design, design files and design-to-code handoff |
| Context7 | Current framework/library documentation |
| Firecrawl / TinyFish / web search | External research, page extraction and authorised browser workflows |
| GitBook | Documentation-site work when explicitly in scope and connected |
| Linear | Optional planning mirror; GitHub remains canonical |
| GitLab | Secondary repo/CI tasks only when explicitly required |
| Manufact | MCP server/deployment management; not the default app deployer |
| 3Min API | Approved API prototypes/management experiments; not the production FastAPI backend by default |
| OpenAI Platform | OpenAI API project/key administration when explicitly requested; API usage may cost money |
| Files / Library | Search and read project documents and reports |
| Plugin Management | Discover/manage available integrations; installing or connecting requires owner action |
| Automations | Approved reminders/monitoring of a clear future dependency; not an autonomous code dispatcher |

**Integration truth:** the presence of a plugin or a user's separate AI subscription does not prove the provider is connected to this chat, has repository access, or can execute tasks. Verify each capability before assigning work. Until then, use copy/paste task briefs and GitHub handoffs.

## 3. Work allocation

| Workstream | Accountable owner | Independent support / reviewer |
|---|---|---|
| Product priorities and acceptance | Project owner | ChatGPT |
| Architecture, technical strategy and cross-module design | ChatGPT | Gemini and Claude challenge; Perplexity researches external facts |
| Task decomposition, issue creation, path reservation and coordination | ChatGPT | Relevant agent |
| Routine implementation that ChatGPT can safely perform through authorised GitHub tools | ChatGPT | Gemini or Claude review according to risk |
| Assigned code edits in Perplexity's accessible workspace | Perplexity (only when explicitly assigned) | ChatGPT reviews; Perplexity does not commit/push |
| Independent module audits and second opinions | Gemini | ChatGPT consolidates findings |
| Complex backend, transactions, concurrency and data-integrity engineering | Claude or ChatGPT, chosen per issue | Gemini/Perplexity read-only review |
| SQL/schema/migration/runner/database CI authoring | Claude by default | ChatGPT coordinates; owner approves |
| External documentation, vendor/API, security and Indian compliance research | Perplexity | ChatGPT validates sources |
| Cloud architecture and infrastructure analysis | ChatGPT coordinates; GCP/AWS selected per approved target | Gemini/Claude review; owner approves spend/change |
| Frontend/backend builds and automated tests | GitHub Actions or an approved terminal | ChatGPT reviews exact run and commit |
| PR integration, release readiness and final audit | ChatGPT | Independent reviewer; owner decides |
| Merge and production deployment | Owner approval required; ChatGPT may execute only within approved permissions | Owner retains final authority |

**No role overlap:** ChatGPT creates one issue per bounded task, names one implementation owner and reserves paths. A reviewer does not edit those paths. If a second agent finds a fix, ChatGPT creates a separate issue or records a review comment; no parallel edits to the same files.

## 4. Standard end-to-end workflow

1. **Intake:** capture the request in GitHub; inspect existing issues, PRs, branch state and current path reservations before creating anything.
2. **Plan:** ChatGPT defines objective, impact, scope, owner, reviewer, base branch/SHA, allowed paths, protected paths, dependencies, acceptance criteria, tests and approval gates.
3. **Classify:** mark the task as non-schema or schema/database, and separately identify infrastructure, security, paid usage or production impact.
4. **Assign:** one accountable owner. ChatGPT remains the overall lead. Gemini/Claude/Perplexity receive separate, non-overlapping tasks; Copilot remains standby.
5. **Execute:** work on a feature branch from latest `main`; post progress and evidence in the same GitHub issue. Perplexity may edit only its assigned code and must not commit/push.
6. **Audit:** a different agent reviews the diff read-only. Use Gemini for independent module/logic challenge, Claude for complex backend/database risk, and Perplexity for external source verification.
7. **Integrate:** ChatGPT checks full diff, API contracts, business rules, security, regression risk, documentation and acceptance criteria.
8. **Verify:** run frontend build and backend tests separately. Prefer GitHub Actions when Codespaces is unavailable. Report terminal-only checks as NOT RUN if no approved runner exists. Never infer a pass.
9. **PR:** keep a focused branch and PR; link the issue, list exact files, tests actually run, CI run/commit SHA, schema/deployment impact and risks.
10. **Approve and release:** owner approves merge/production actions. Merged does not mean deployed. Deployment and post-deployment health/end-to-end verification are separate steps.

### Task handoff format

```text
Issue:
Task owner:
Reviewer:
Task type: research / audit / implementation / QA / documentation
Base branch + SHA:
Allowed paths:
Protected paths:
Objective and acceptance criteria:
Dependencies:
Commands/tests expected:
Evidence and results (PASS / FAIL / NOT VERIFIED):
Files changed:
Risks / blockers:
Next owner:
Schema / infrastructure / paid / production impact:
Approval required:
```

## 5. Codespaces, Copilot and execution reality

- Codespaces usage is currently exhausted. No top-up or paid compute without explicit owner approval.
- Copilot stays on standby and is not required to complete work.
- ChatGPT can use the GitHub integration for supported repository actions, but that is not the same as having a live shell, Codespace or production terminal.
- Use GitHub Actions for supported deterministic checks. If a test requires an interactive shell or secrets/environment unavailable to Actions, mark it NOT RUN and request an approved execution route.
- Gemini, Claude and Perplexity are separate products/sessions unless a verified connector is actually available. GitHub comments and task briefs are the handoff mechanism; no background agent-to-agent dispatch is assumed.

## 6. Repository and database safeguards

- Start from latest `main`; create focused feature branches. Never push directly to `main`.
- Never overwrite or revert unrelated working code. One new migration file per approved schema change; SQL must be additive and idempotent under the repository's current rules.
- Never edit, rename, delete or reformat historical/applied migrations. Do not touch `backend/schema/000_baseline_schema.sql` or `backend/schema/009_loyalty_programme.sql`.
- Do not change `backend/schema_required.txt`, `backend/scripts/apply_schema.sh` or migration CI outside the approved database-owner process.
- Read `docs/DATABASE_CHANGE_RULES.md` and `CLAUDE.md` before any database/schema/migration work. Claude is the designated default SQL/schema/runner author unless the owner records a specific exception.
- No production data writes, destructive SQL, live migrations, credential/role changes, secret rotation, infrastructure changes or deployment without explicit owner approval and documented preflight.
- Preserve the established targets unless a verified owner-approved change says otherwise: backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, AWS EC2 + Nginx + Gunicorn backend, Amplify frontend and existing systemd service/timer.
- Google Cloud remains an evaluated/available cloud workstream, not an automatic replacement for the current AWS production setup.

## 7. Diagnostic and verification order

1. GitHub issue/PR/commit/CI inspection.
2. Swagger/OpenAPI first for route, request/response, auth and status-code defects.
3. Source trace: UI → API client → FastAPI route → service/business rules → SQL/data model.
4. Use an approved terminal or GitHub Actions for execution; do not assume Codespaces is available.
5. Use AWS/GCP consoles only when evidence points to hosting, runtime, networking, IAM, logs, environment or infrastructure.
6. Use Amplify for current frontend hosting/build symptoms.
7. Production database state requires owner-approved read-only preflight; Git is not proof of live DB state.
8. Verify exact commit, required CI checks, targeted tests and relevant user journey.
9. Deploy only after separate owner approval; then verify health and end-to-end behaviour.

## 8. Status and stop conditions

Use only: `READY`, `ACKNOWLEDGED`, `IN PROGRESS`, `BLOCKED`, `REVIEW`, `COMPLETE`.

- `COMPLETE` means acceptance criteria and evidence are recorded; it does not mean merged or deployed.
- Report PASS, FAIL or NOT VERIFIED. Never claim an unrun test, unverified integration, agent dispatch, repository permission, merge or deployment.
- Stop if paths overlap, required access is missing, the base SHA is stale, protected assets are implicated, a task needs unapproved spend, or production/schema approval is unclear.
- If a preferred agent is unavailable, ChatGPT reassigns the same issue to one available owner after checking for partial changes. Do not create duplicate parallel implementations.
- A GitHub timer/label cannot cause an external AI to wake up and execute. True unattended dispatch requires a separately configured, authorised and tested API/agent integration with cost and permission controls.

## 9. Maintenance

This document is the canonical role and workflow source. Update `docs/AI_TEAM_COLLABORATION.md`, `docs/AI_AGENT_TASK_CHECK_COMMANDS.md`, `AGENTS.md`, and Copilot instructions whenever the operating model changes. Keep role descriptions consistent; do not maintain competing role tables.
