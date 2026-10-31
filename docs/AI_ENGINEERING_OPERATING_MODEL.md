# Super Bajaar — AI Engineering Operating Model

> **Status: Active — merged to `main` on 31 October 2026.** This is the canonical AI-team operating contract for Super Bajaar. GitHub is the shared system of record. Separate AI chats do not communicate directly.

## 1. Command, accountability and principles

### Verified access model and execution limits

The repository is public. Public visibility means an agent can read public GitHub pages and files; it does **not** grant authenticated write access, provider dispatch, issue acknowledgement or permission to change production.

| Agent | Access that may be relied on | Permitted operating mode |
|---|---|---|
| **ChatGPT** | Public read access plus the connected GitHub integration's available read/write operations. Verify each operation. | CTO coordination; may create branches, edit files, comment and open PRs through authorised tools. No direct push to `main`; merge/deploy only under owner approval and repository policy. |
| **GitHub Copilot** | Public repository visibility; coding-agent write/branch/PR capability only when the repository/account feature is enabled and GitHub actually starts an agent session. | Bounded implementation on its assigned issue. A label or @mention alone is not dispatch evidence. |
| **Google Gemini (main)** | Public repository read access when its own browsing/session can open the repository. No GitHub write integration is assumed. | Read-only audit/review by default. Return findings; do not claim edits, commits or PRs. |
| **Perplexity** | Public repository/documentation read access where available in its session, plus external research access. No GitHub write integration is assumed. | External research and source verification only. Do not modify repository files or claim issue changes. |
| **Claude** | Public repository read access; may return complete files or patches. Direct GitHub write/commit/PR access is not assumed. | Complex backend/data-integrity analysis and designated SQL/schema/migration/runner authoring. ChatGPT integrates returned patches through an authorised feature branch. |

Before relying on access, each agent must verify the exact repository, issue/file and operation in its own session. If unavailable, report the precise limitation; do not infer access from another agent's connection. Repository access never grants production, secrets, database or deployment access.

### Role-specific start notes — 31 October 2026

These notes clarify current handoffs; live GitHub issue bodies and comments override them if state changes.

- **ChatGPT:** coordinate #207 (Copilot), #206 (Gemini) and #209 (Perplexity); inspect live GitHub state before reporting progress; integrate and independently review deliverables. Keep one owner per task.
- **GitHub Copilot:** #207 is its bounded implementation assignment for the 60-second fallback dispatch. Do not touch #176 or Claude's database/schema responsibilities. Start only after checking the live issue, acknowledging it and verifying a supported Copilot coding-agent session.
- **Google Gemini:** #206 is the read-only catalogue/product/attribute and inventory audit assignment. Do not take ownership of #207 or #209, do not edit code, and report exact evidence and unknowns.
- **Perplexity:** #209 is the P2 external research assignment, Status READY. Acknowledge it in the issue before research. Item B is documented GitHub facts only for #207; item D is external design references only for #206; item E must distinguish current law, future-effective notified provisions and proposals/historical rules.
- **Claude:** pull only an explicitly routed READY Claude issue. Do not assume #206, #207 or #209 belongs to Claude. For SQL/schema/runner work, follow `CLAUDE.md` and owner approval gates.

- **Project owner:** final authority for product priorities, access, paid usage, merge, production data, secrets, infrastructure and release approval.
- **ChatGPT — CTO / coordinator:** architecture, task decomposition, single-owner allocation, dependency management, cross-agent handoffs, integration review, evidence review and documentation governance. It does not claim another agent's execution or unrun tests.
- **One task = one accountable owner.** Reviewers may challenge work read-only; they do not become co-implementers.
- **One active writer per file set.** Reserve exact paths in the issue. No concurrent edits to the same files or branch.
- **GitHub is shared memory:** issues hold scope and decisions; PRs hold diffs and review; Actions hold CI evidence; dated project updates hold accepted decisions.
- No direct push to `main`; no self-merge; no bypass of branch protection; no deployment or production mutation without explicit owner approval.
- Existing assignments remain in force. Do not reassign or duplicate Copilot issue #176 (FastAPI route-registration audit).


## 2. Optional contributors and 60-second fallback

**A contributor is an optional execution resource, never a blocker or mandatory dependency.** The task must have a fallback owner before it is dispatched.

1. Create the issue with one preferred contributor and one named fallback (normally ChatGPT as coordinator, provided the required tools/access are available).
2. Start a **60-second acknowledgement window** when the task is actually delivered to the preferred contributor. Record the dispatch timestamp and delivery evidence in the issue. Merely creating an issue does not start the clock.
3. If the contributor acknowledges within 60 seconds, it may proceed within the reserved scope. Acknowledgement means acceptance of the task, not completion.
4. If there is no acknowledgement after 60 seconds, mark the preferred contributor `NO RESPONSE / OPTIONAL` and activate the fallback owner. Do not wait indefinitely and do not create a duplicate parallel implementation.
5. If the preferred contributor explicitly declines, reports unavailable access, or cannot meet the task's required capability, activate the fallback immediately; do not wait for the timer.
6. The fallback inherits the same issue, acceptance criteria, allowed paths, protected paths, base SHA and approval gates. It must first check whether the preferred contributor made any changes before writing.
7. If ChatGPT cannot directly execute in an available approved environment, it must take the next permitted action (for example, use an available GitHub/CI integration or create a tightly scoped fallback assignment for an available agent) and report the actual blocker. It must never claim that an unattended task was executed.
8. The timeout is an acknowledgement/fallback rule, **not permission to bypass owner approval** for schema, production data, secrets, infrastructure, paid usage, merge or deployment.

### Automation boundary

A GitHub Actions timer can detect a missing acknowledgement, add a status label/comment and notify the fallback owner. It cannot, by itself, cause a ChatGPT conversation or an external AI agent to execute code. True unattended AI dispatch requires a separately configured and authorised agent/API integration with credentials, provider limits, cost controls and scoped repository permissions. Until that integration is implemented and verified, the 60-second fallback is coordinator-driven; do not describe it as an already-running autonomous dispatcher.

## 3. Agent and tool register

| Contributor | Primary role and responsibilities | Boundaries / status |
|---|---|---|
| **ChatGPT** | **CTO and engineering lead.** Own architecture, technical strategy, requirement analysis, decomposition, GitHub issue creation/allocation, dependency management, path reservation, cross-agent coordination, integration design, code/PR review, QA strategy, CI evidence review, documentation governance, release readiness and PR merging when authorised. | Does not claim other agents' execution. Claude remains designated SQL/schema author. No unapproved production, paid usage, infrastructure or deployment actions. |
| **GitHub Copilot** | **Primary bounded coding and implementation agent.** Own assigned React/Vite frontend work, non-schema FastAPI/API/service implementation, scoped bug fixes, integrations, refactoring, tests, implementation documentation, feature branches and PR preparation. | No protected schema/migration/runner changes, production data or infrastructure. No direct main, self-merge or deployment. Cloud-agent capability must be verified for the actual account/repository. |
| **Google Gemini (main)** | **Independent auditor and quality challenger.** Own read-only audits of catalogue, products, variants, attributes, inventory, FIFO/FEFO/expiry, frontend/API/backend flows, security, performance and test gaps; independently review Copilot/Claude PRs; provide reproducible evidence. May implement a separate non-schema fix only through a new ChatGPT-assigned issue with distinct reserved paths. | Audit/review is read-only. No concurrent editing of Copilot/Claude files and no schema/migration/runner ownership. Repository access must be verified. |
| **Perplexity** | **External research and source-verification specialist.** Own official documentation, API/vendor capability checks, release notes, security advisories, technical comparisons, pricing/plan checks and assigned Indian e-commerce/GST/consumer/privacy compliance research. Deliver source-backed briefs with dates and limitations. | Research-only. No code edits, commits, migrations or implementation PRs. Do not assume private repository access. |
| **Claude** | **Complex engineering and database specialist.** Own difficult backend problems involving transactions, concurrency, data integrity, performance and cross-module complexity; SQL/schema design, additive migrations, migration runner and database CI under `CLAUDE.md` and database rules. | No historical/applied migration edits; no production SQL or release without explicit approval and preflight. No overlapping path ownership. |
| **Gemini CLI** | Optional terminal interface to Gemini for approved terminal-based work after authentication and model execution are verified. | Same Gemini model family, not a second independent agent or separate task owner. |
| **Antigravity** | Experimental alternative agent/IDE workflow for sandbox evaluation only after account access and repository permissions are verified. | No active production assignment until verified. |
| **GitHub Actions** | Deterministic CI: frontend/backend checks, tests, database-file validation, security scans and policy checks. | Automation, not an AI agent; green CI is not production verification. |
| **GitHub** | Canonical source of truth for issues, labels, branches, commits, PRs, reviews, Actions and permissions. | Not an AI worker; issue labels do not prove delivery or execution. |
| **Codespaces** | Interactive development terminal for editing and running checks when available. | Current usage budget is exhausted; no top-up or paid compute without owner approval. |
| **Context7** | Version-specific framework/library documentation retrieval for implementation and review. | Reference tool only; not an implementation owner or test runner. |
| **Firecrawl** | Public web-page and documentation extraction for research. | Research support only; no repository writes. |
| **TinyFish** | Browser-based research and user-authorised website workflows. | Not a code owner or production deployment system. |
| **Manufact** | Authorised MCP server and deployment management. | Not the default Super Bajaar application deployer; infrastructure changes require approval. |
| **Linear** | Optional planning mirror when explicitly requested. | GitHub remains canonical; avoid duplicate task ownership. |
| **GitLab** | Secondary repository/CI platform for explicitly scoped tasks. | Not part of the default Super Bajaar delivery path. |
| **3Min API** | API prototyping/management for separately approved experiments. | Not the production FastAPI backend by default. |
| **AWS EC2 / SSM** | Runtime/host investigation and approved backend operations when evidence points to infrastructure. | Not the first stop for ordinary source/API defects. |
| **AWS Amplify** | Frontend hosting/build investigation and separately approved frontend releases. | Not the backend runtime or a coding agent. |
| **Swagger / OpenAPI** | First diagnostic tool for API route, request/response, authentication and status-code defects. | API contract explorer; not proof of complete end-to-end correctness. |
| **Figma** | UI/UX source of truth for approved screens, components, variables, design tokens and design-to-code handoff. | Use when the task references a Figma file or design deliverable; never invent design approval or alter files without the relevant user request. |
| **GitBook** | Authoring, structuring and reviewing a separate documentation site when one is connected and explicitly in scope. | GitHub Markdown remains the repo source of truth unless a GitBook sync workflow is explicitly established. |
| **OpenAI Platform** | Manage OpenAI API project/key lifecycle and platform setup when explicitly requested. | Never request or expose API keys in chat; API use may be billable and requires owner approval. |
| **Plugin Management** | Discover connected integrations, inspect permissions and suggest relevant connections. | Connection/install always requires owner action; a listed plugin is not proof that an account is connected or authorised. |
| **Conversation Files / Library** | Search and read project documents, prior reports and uploaded references. | File content is evidence only for the referenced version; it does not grant repository or production access. |
| **Superpowers workflow skills** | Apply disciplined brainstorming, planning, debugging, test-driven development, code review and verification practices. | Process guidance, not an external coding agent or an execution environment. |
| **NVIDIA tools/skills** | Specialised CUDA/GPU/NIM/NeMo work if Super Bajaar later adopts NVIDIA technology. | Not relevant to ordinary current React/FastAPI/PostgreSQL work unless a task explicitly introduces NVIDIA components. |
| **Zuora tools/skills** | Zuora Billing/Revenue/CPQ API design and integration if the product adopts Zuora. | Not a default payment, subscription or accounting integration; do not introduce it without an approved product requirement. |

### Identity and ownership rules

- Gemini main and Gemini CLI are one model family/access route, not two independent AI contributors.
- One issue has one accountable implementation owner. Reviewers remain read-only.
- ChatGPT allocates paths before work begins. Gemini may implement only a separately assigned non-schema issue after audit; it must not overlap Copilot or Claude.
- Claude retains database/schema/migration/runner ownership under `CLAUDE.md`.
- Perplexity is a research specialist, not a coding agent.
- GitHub Actions, Context7, Firecrawl, TinyFish, Manufact, Linear, GitLab, 3Min API, Codespaces, AWS and Swagger are supporting tools/services, not substitutes for an accountable AI task owner.

## 4. Exclusive work allocation

| Workstream | Accountable owner | Reviewer / support |
|---|---|---|
| Product priorities and acceptance | Project owner | ChatGPT |
| Architecture, strategy and cross-module design | ChatGPT | Gemini read-only challenge; Perplexity for external facts |
| Requirement analysis, task decomposition and GitHub allocation | ChatGPT | Relevant domain agent |
| Routine React/Vite frontend implementation | Copilot | Gemini read-only review; ChatGPT integration |
| Bounded non-schema FastAPI/API/service implementation | Copilot | Gemini read-only review; ChatGPT integration |
| Independent catalogue, product, variant and attribute audit | Gemini (read-only) | ChatGPT |
| Independent inventory, batch, FIFO/FEFO and expiry audit | Gemini (read-only) | ChatGPT; Claude for complex database implications |
| Independent UI/API/backend/security/performance audit, excluding Copilot #176 | Gemini (read-only) | ChatGPT |
| FastAPI route-registration audit already assigned in #176 | Copilot | ChatGPT reviews evidence; Gemini does not duplicate |
| Separate non-schema fix discovered by Gemini | Gemini only when ChatGPT creates a distinct issue and reserves paths | ChatGPT; Copilot does not edit those paths |
| Complex backend, transaction, concurrency and data-integrity issue | Claude | ChatGPT; Gemini read-only challenge |
| SQL/schema/migrations/runner/database CI | Claude | ChatGPT coordinates; owner approves |
| External official documentation, vendor/API capability, security and Indian compliance research | Perplexity | ChatGPT validates sources |
| Library/framework documentation lookup | Context7 | Implementing agent remains accountable |
| CI, tests, builds, security and policy gates | GitHub Actions | ChatGPT reviews exact run/commit |
| Integration, release readiness and final evidence review | ChatGPT | Gemini read-only review; owner decides |
| PR merge | ChatGPT executes only when owner policy/approval and all required gates are satisfied | Owner retains final authority |
| Production deployment and post-deploy verification | ChatGPT coordinates only after explicit owner approval | Claude supports complex database release; owner authorises |

**Allocation rule:** Gemini's audit and review assignments are read-only. If an audit discovers a fix, ChatGPT creates a new implementation issue, reserves non-overlapping paths and chooses exactly one implementation owner. Copilot handles routine bounded non-schema changes; Claude handles complex backend/database work. Perplexity does not implement repository code.
## 5. Mandatory GitHub task workflow

### A. Intake and allocation

1. Record the request as a GitHub issue or link it to an existing issue.
2. Read `README.md`, `AGENTS.md`, this document, and task-specific canonical docs.
3. Identify affected modules, exact allowed paths, protected paths, dependencies, acceptance criteria, verification and production/schema risk.
4. Check open issues/PRs and current assignments before allocating.
5. Name **one accountable agent** and one independent reviewer. Do not create duplicate tasks for the same scope.
6. If scope overlaps an existing assignment, stop and coordinate through that issue rather than opening a competing task.

### B. Issue template — required fields

Every agent issue must state:

- Objective and user impact.
- Task type: research / read-only audit / implementation / QA / security / documentation.
- Primary accountable agent and independent reviewer.
- Repository, base branch and starting commit SHA.
- Allowed paths (or explicit read-only scope).
- Protected paths/systems.
- Dependencies and related issues/PRs.
- Acceptance criteria and exact verification expected.
- Expected output and next owner.
- Approval gates for schema, production, credentials, paid usage, infrastructure or deployment.

Use the repository agent-work issue form if/when its governance PR is merged. Until then, include these fields in the issue body manually.

### C. Execution and communication

1. The agent acknowledges the issue and confirms scope before work.
2. It checks the latest `main` and uses a focused feature branch for implementation.
3. It works only within its allowed paths; audit/research tasks remain read-only.
4. It posts concise progress, blockers and evidence in the same GitHub issue. Separate AI chat conversations are not shared.
5. It opens a PR for code/document changes and links the originating issue.
6. The reviewer examines the diff read-only and records findings in the PR.
7. The author resolves review feedback; no other agent silently edits its branch.
8. ChatGPT checks cross-module compatibility, docs, schema impact and evidence.
9. The owner decides whether to merge. Deployment is a separate approval.

### D. Required completion report

```text
Issue / task ID:
Accountable agent:
Task type and access mode:
Base branch + starting SHA:
Allowed paths:
Files inspected:
Files changed (or NONE):
Findings / changes:
Acceptance criteria: PASS / FAIL / NOT VERIFIED
Commands and tests actually run:
Exact CI run + commit SHA:
Risks / unresolved questions:
Next owner / dependency:
Production or schema impact: NONE / PROPOSED / APPROVED / VERIFIED
```

Never report tests as passed if they were not executed. If no terminal is available, state NOT RUN and use GitHub Actions or another approved execution environment when available.

## 6. Non-overlap and file-reservation protocol

- One issue reserves one path set. Before editing, the agent checks open issues and PRs for overlapping paths.
- A read-only auditor may inspect an active implementation's diff but cannot edit its files.
- A reviewer may comment on a PR but cannot push commits to the author's branch.
- If an unexpected shared dependency is discovered, stop edits, comment on the issue, and ask ChatGPT to split/reassign the work.
- Keep implementation batches small (normally 2–3 related files where practical); split larger work into sequential accepted batches.
- Existing assignments are grandfathered until completed or explicitly reallocated by the owner.
- Do not use labels or agent names as proof of execution; record actual provider/session/commit evidence when available.

## 7. Repository, schema and production safeguards

- Feature branches only; no direct push to `main`.
- Owner retains merge and deployment authority. A connected integration does not override repository policy or branch protection.
- Claude remains designated default SQL/schema/migration/runner author under `CLAUDE.md`.
- Do not edit, rename, delete or reformat existing/applied migrations. Follow `docs/DATABASE_CHANGE_RULES.md`, the unique numbering rule, additive/idempotent SQL and one-new-file-per-change requirement.
- Do not touch `backend/schema/000_baseline_schema.sql` or `backend/schema/009_loyalty_programme.sql`.
- Do not change `backend/schema_required.txt`, `backend/scripts/apply_schema.sh` or migration CI except through Claude's approved scoped task and owner approval.
- No production data writes, destructive SQL, production migrations, secret rotation, permission changes, infrastructure changes or deployments without explicit owner approval and documented preflight.
- Preserve backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, EC2/Nginx/Gunicorn, Amplify and existing systemd service/timer unless owner approves a verified change.
- Never expose credentials, tokens, customer/payment data or `.env` values.
- No new paid service, API spend, AI usage budget or Codespaces top-up without owner approval.
- Merged is not deployed. CI pass is not production verification.

## 8. Diagnostic and verification workflow

1. **GitHub first:** inspect issue, PR, changed files, branch, commit and CI.
2. **Swagger/OpenAPI first for API defects:** inspect route, auth, request/response, status and reproduce contract failures before editing code.
3. **Source-level diagnosis:** trace UI → API client → FastAPI route → service/business rules → SQL/data model.
4. **Execution:** use an available approved terminal or CI runner. Codespaces is currently unavailable due to exhausted budget; do not assume a live shell. Prefer GitHub Actions for repeatable repository checks when the workflow supports them.
5. **AWS only with evidence:** runtime, service, environment, networking, logs, Nginx, Gunicorn, systemd or EC2 issues.
6. **Amplify for frontend hosting/build symptoms.**
7. **Database live state:** owner-approved read-only preflight only. Never infer production schema or backup state from Git.
8. **Independent verification:** exact commit, required CI checks, targeted tests and relevant user journey evidence.
9. **Deployment:** separately approved, followed by environment-specific health and end-to-end verification.

## 9. AI usage, cost and entitlement controls

- No agent is assumed to have unlimited tokens, requests, credits, context or repository permissions.
- **ChatGPT:** usage depends on the owner's ChatGPT plan, selected model and current account limits. Do not quote a fixed token allowance without checking account/product documentation.
- **Gemini:** main Gemini access and Gemini CLI consume the applicable Gemini account/API quota; CLI is not a second independent quota. API limits depend on model, tier, project and current AI Studio terms.
- **Antigravity:** account/model/agent limits depend on the actual plan and current product policy; verify in the account before work.
- **Claude:** subscription message limits or API input/output-token billing depend on the actual account and model; verify before large jobs.
- **Copilot:** limits depend on the actual Copilot plan and AI-credit/model billing. Check live account allowance, reset and paid-overage settings; do not infer plan from repository access.
- **Perplexity:** search/research allowances depend on Standard/Pro/Enterprise plan and feature; verify live account limits.
- **Codespaces:** current usage budget is exhausted. Do not resume, top up or trigger billable compute without explicit approval.
- Context7, Firecrawl, TinyFish, Manufact, Linear, GitLab and 3Min API have product/plan-specific limits; use only within the connected account's verified allowance.
- Before any potentially billable agent run, state the expected purpose and likely cost/credit exposure if known. If unknown, start with a small task and inspect usage afterwards.
- Keep paid overage disabled or budget-capped where the owner wants no surprise charges. Never store or print API keys in GitHub issues, PRs or chat.

### Usage reporting

For any task that materially consumes paid/API credits, record provider, model/tool, approximate usage if the provider exposes it, and whether it was free-tier or billable. Do not invent token counts or pricing. Review actual usage dashboards for exact remaining balances and resets.

## 10. Stop conditions and escalation

Pause and ask the owner if:
- issue/PR scope conflicts with another active assignment;
- a task needs access that has not been verified;
- the agent cannot read required docs or the assigned branch;
- protected schema, production data, credentials, infrastructure or permissions are implicated;
- the task would incur unapproved paid usage;
- test evidence contradicts the proposed fix;
- an agent proposes broad refactoring or touches files outside its allowlist.

Record the blocker, impact, safe options and decision needed in the originating issue.

## 11. Current operational baseline

- GitHub repository: `siinghniibandhan-wq/superbajaar`.
- GitHub is the shared coordination centre.
- Codespaces budget: exhausted; no further Codespaces work until allowance returns or owner approves a different budget.
- Gemini main: owner reports repository access; verify access to the specific issue/PR before assigning.
- Gemini CLI: installed in the prior Codespace, but successful authentication/model response was not verified; no active assignment.
- Antigravity CLI: installed earlier; authentication/repository write access not verified; experimental only.
- Copilot: preserve current GitHub issue assignments; #176 remains assigned to its existing route-registration audit.
- Claude: designated SQL/schema author per `CLAUDE.md`.
- Perplexity: owner reports connected and GitHub repository access; use for source-backed research, not code changes.

**Maintenance:** Update this policy when actual access, agent capabilities, owner decisions or usage plans change. Record the date and evidence. This document does not grant permissions or authorize spending, merges or deployment.


## 12. User-invoked agent task checking

The standard pull-based activation protocol and copy/paste commands for Copilot, Gemini, Perplexity and ChatGPT are maintained in `docs/AI_AGENT_TASK_CHECK_COMMANDS.md`.

- Route issues with exactly one `agent:<name>` label and an explicit accountable-owner field.
- Each agent checks its own open assignments when the user invokes its activation prompt; it reports "no open assignments" when none match.
- Each agent acknowledges and updates the same GitHub issue with progress, blockers and evidence.
- An issue/label/@mention is not proof of delivery, acknowledgement or execution. Copilot must be started through a supported Copilot agent mechanism; Gemini and Perplexity require the user to invoke their connected AI and ask it to pull its tasks.
- This is user-invoked polling, not background polling. Do not claim automatic monitoring or dispatch unless a separately configured provider integration has been tested.
- Start the 60-second fallback only after actual delivery to the preferred contributor is evidenced.
