# Super Bajaar — AI Engineering Operating Model

> **Status: Proposed for owner review.** This document becomes the canonical AI-team operating contract only after its pull request is approved and merged. GitHub is the shared system of record. Separate AI chats do not communicate directly.

## 1. Command, accountability and principles

- **Project owner:** final authority for product priorities, access, paid usage, merge, production data, secrets, infrastructure and release approval.
- **ChatGPT — CTO / coordinator:** architecture, task decomposition, single-owner allocation, dependency management, cross-agent handoffs, integration review, evidence review and documentation governance. It does not claim another agent's execution or unrun tests.
- **One task = one accountable owner.** Reviewers may challenge work read-only; they do not become co-implementers.
- **One active writer per file set.** Reserve exact paths in the issue. No concurrent edits to the same files or branch.
- **GitHub is shared memory:** issues hold scope and decisions; PRs hold diffs and review; Actions hold CI evidence; dated project updates hold accepted decisions.
- No direct push to `main`; no self-merge; no bypass of branch protection; no deployment or production mutation without explicit owner approval.
- Existing assignments remain in force. Do not reassign or duplicate Copilot issue #176 (FastAPI route-registration audit).


## 2A. Optional contributors and 60-second fallback

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

## 2. Agent and tool register

| Contributor | Exclusive responsibility | Allowed work | Explicit exclusions / current status |
|---|---|---|---|
| **ChatGPT** | CTO, architecture and coordination | Design decisions, issue briefs, work allocation, integration review, PR/evidence review, documentation and final acceptance recommendation | Does not claim work done by agents; does not approve its own work, merge, deploy or mutate production |
| **Google Gemini (main)** | Independent repository audit and technical findings | Read-only audit of allocated modules: product/catalogue/attributes, inventory/FIFO-FEFO/expiry, frontend/backend/API, security, performance, tests and documentation; report reproducible evidence and recommendations | Audit phase is read-only. No code edits, branches, migrations or production actions during audit. Repository access is owner-reported; verify issue/PR visibility before relying on it |
| **Google Gemini CLI (`gemini`)** | Alternate terminal interface to Gemini models | May be used later for terminal-based repository work if authenticated and tested | Currently installed in a Codespace but model response/repository-agent execution is unverified; Codespaces budget is exhausted. It is not a second independent AI or separate task owner. No current assignments |
| **Google Antigravity CLI (`agy`)** | Experimental alternative Google coding-agent interface | Sandbox evaluation only after authentication and repository permissions are verified | Installed earlier; authentication and repo write access unverified. No production assignments and no duplicate Gemini tasks |
| **Claude** | Designated database/schema/migration/runner author; complex backend implementation | Database design, additive migration drafts, migration runner/database CI work under `CLAUDE.md`; complex backend implementation on separately reserved paths | No edits to another agent's reserved files; no applied migration edits; no production SQL without owner approval/preflight |
| **GitHub Copilot** | Existing GitHub assignments and bounded non-schema implementation | Continue existing assigned issues; bounded implementation, tests and PR preparation on exact allowed paths; GitHub issue/PR operations only where account and repository permissions permit | Preserve existing assignments, especially #176. No protected SQL/runner authoring, no direct main, no self-merge, no deployment. Cloud-agent and merge capability are not assumed from a connected account |
| **Perplexity AI** | Independent external research and source verification | Official docs, vendor release notes, security advisories, technical comparisons, pricing/plan fact checks and source-backed research briefs | No repository code edits, commits, migrations or PR implementation. Private repo access is not assumed; use only access actually verified or public/owner-provided material |
| **GitHub Actions** | Deterministic automated quality gates | CI, tests, builds, migration checks, security scans and governance validation | Not an AI agent; green CI is not production verification |
| **GitHub** | Shared source of truth and workflow system | Issues, branch/PR/commit/review records, Actions, permissions and protected-branch enforcement | GitHub integration does not itself provide a terminal or prove a coding agent can execute tests |
| **Codespaces** | Optional interactive development terminal | Repository editing, shell, builds and tests when available | Current usage budget exhausted. Do not restart/top-up or incur paid usage without owner approval. Not required for GitHub issue/PR communication |
| **Context7** | Version-aware technical documentation retrieval | Resolve official library docs and query exact installed versions for implementation/review | Reference source only; not an agent, test runner or source of truth |
| **Firecrawl** | Web extraction and research support | Retrieve public documentation/pages for research tasks | No repository writes or implementation ownership |
| **TinyFish** | Browser automation and website workflow research | User-authorized browser research and multi-step website checks | Not a code owner; no production actions without task-specific approval |
| **Manufact** | MCP/server/deployment infrastructure management | Inspect/manage explicitly authorised MCP servers and deployments | Not a default app deployment tool; no infrastructure changes without approval |
| **Linear** | Optional planning mirror | Planning only if specifically requested | GitHub remains canonical; do not duplicate task ownership |
| **GitLab** | Secondary repository platform | Only explicitly authorised GitLab work | Not part of the active Super Bajaar delivery path unless a task requires it |
| **3Min API** | API prototyping/management | Separate API prototypes when explicitly approved | Not a default production backend or an implementation owner |

**Identity rule:** Gemini and Gemini CLI are the same model family/access route for this plan, not two independent reasoning agents. Do not count them as two AI brains or allocate separate duplicate work. Antigravity is a separate interface/product and remains experimental.

## 3. Exclusive work allocation

| Workstream | Accountable owner | Reviewer / support |
|---|---|---|
| Product priorities and acceptance | Project owner | ChatGPT |
| Architecture and cross-module design | ChatGPT | Gemini read-only challenge; Perplexity for external facts |
| Product catalogue, attributes, variants audit | Gemini (read-only) | ChatGPT |
| Inventory, batch, FIFO/FEFO and expiry audit | Gemini (read-only) | ChatGPT |
| Frontend, backend and API independent audit | Gemini (read-only), excluding existing Copilot #176 scope | ChatGPT |
| FastAPI route-registration audit already assigned in #176 | Copilot | ChatGPT reviews evidence |
| SQL/schema/migrations/runner/database CI | Claude | ChatGPT coordinates; owner approves |
| Complex backend implementation | Claude, only on reserved paths | Copilot may implement separate bounded tasks on different paths |
| Bounded non-schema code tasks already assigned | Copilot | ChatGPT |
| New non-schema implementation | ChatGPT assigns exactly one of Claude or Copilot after path reservation | Other agent may review read-only |
| External docs, vendor policy, pricing, security advisory research | Perplexity | ChatGPT validates sources |
| Current package/API documentation lookup | Context7 as a reference tool | Implementing agent remains accountable |
| CI execution and repeatable checks | GitHub Actions | ChatGPT reviews exact run/commit |
| Integration, release readiness and final evidence review | ChatGPT | Owner decides merge/release |
| Merge and production release | Project owner / authorised human | Required reviews and CI |

No role in this table grants new repository permissions or subscription entitlements. Verify access and plan capability before depending on a feature.

## 4. Mandatory GitHub task workflow

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

## 5. Non-overlap and file-reservation protocol

- One issue reserves one path set. Before editing, the agent checks open issues and PRs for overlapping paths.
- A read-only auditor may inspect an active implementation's diff but cannot edit its files.
- A reviewer may comment on a PR but cannot push commits to the author's branch.
- If an unexpected shared dependency is discovered, stop edits, comment on the issue, and ask ChatGPT to split/reassign the work.
- Keep implementation batches small (normally 2–3 related files where practical); split larger work into sequential accepted batches.
- Existing assignments are grandfathered until completed or explicitly reallocated by the owner.
- Do not use labels or agent names as proof of execution; record actual provider/session/commit evidence when available.

## 6. Repository, schema and production safeguards

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

## 7. Diagnostic and verification workflow

1. **GitHub first:** inspect issue, PR, changed files, branch, commit and CI.
2. **Swagger/OpenAPI first for API defects:** inspect route, auth, request/response, status and reproduce contract failures before editing code.
3. **Source-level diagnosis:** trace UI → API client → FastAPI route → service/business rules → SQL/data model.
4. **Execution:** use an available approved terminal or CI runner. Codespaces is currently unavailable due to exhausted budget; do not assume a live shell. Prefer GitHub Actions for repeatable repository checks when the workflow supports them.
5. **AWS only with evidence:** runtime, service, environment, networking, logs, Nginx, Gunicorn, systemd or EC2 issues.
6. **Amplify for frontend hosting/build symptoms.**
7. **Database live state:** owner-approved read-only preflight only. Never infer production schema or backup state from Git.
8. **Independent verification:** exact commit, required CI checks, targeted tests and relevant user journey evidence.
9. **Deployment:** separately approved, followed by environment-specific health and end-to-end verification.

## 8. AI usage, cost and entitlement controls

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

## 9. Stop conditions and escalation

Pause and ask the owner if:
- issue/PR scope conflicts with another active assignment;
- a task needs access that has not been verified;
- the agent cannot read required docs or the assigned branch;
- protected schema, production data, credentials, infrastructure or permissions are implicated;
- the task would incur unapproved paid usage;
- test evidence contradicts the proposed fix;
- an agent proposes broad refactoring or touches files outside its allowlist.

Record the blocker, impact, safe options and decision needed in the originating issue.

## 10. Current operational baseline

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
