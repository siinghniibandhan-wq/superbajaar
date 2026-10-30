
# AI Agent Orchestration — Architecture & Implementation Blueprint

> **Status:** Architecture documented; GitHub-native task validation is staged in PR #177 and is not active on main until the owner merges it.
> **Date:** 31 October 2026
> **Scope:** Superbajaar first; reusable for Financial OS and KPMC after validation.
> **Owner:** Project owner (human) · **Technical coordinator:** ChatGPT
> **Control plane:** Existing GitHub repository, Issues, Pull Requests and GitHub Actions.
> **Constraints:** Mobile-first, free-first, least privilege, no new server/database by default, no direct push to main, owner-controlled merge and production release.

## 1. Executive summary

Build a coordinated multi-agent delivery system in which a shared queue tracks tasks, dependencies, ownership, evidence and handoffs. The coordinator decomposes work into small packages, dispatches independent packages to available agents, keeps safe work moving while long-running work executes, integrates findings and routes completed changes through independent review and CI.

This is an **event-driven, task-oriented team**, not a collection of agents chatting without a shared record. GitHub is the durable source of truth. Separate AI chat histories are private to their providers and are not assumed to be shared.

Start with documented/manual dispatch using existing GitHub capabilities. Automate only after each provider's actual API, mobile access, permissions, cost and quota have been verified. Do not build a custom orchestration server, add a database, or connect every provider at once.

## 2. Goals and non-goals

### Goals
- Keep independent, ready work progressing while another task or CI run is waiting.
- Make ownership, priority, dependency, status and next handoff visible.
- Support agents with distinct roles and bounded permissions.
- Prevent concurrent edits to the same files.
- Preserve findings and decisions in GitHub, not private chat histories.
- Resume from the last verified checkpoint after provider failure.
- Switch to an approved fallback when a primary tool is unavailable or its free quota is exhausted.
- Require evidence for tests, reviews, merges and releases.
- Let the owner monitor and approve work from mobile.
- Start with the existing repository and infrastructure.

### Non-goals for the initial phase
- No autonomous merge to main.
- No autonomous production deployment, migration, data modification or secret rotation.
- No unrestricted agent-to-agent messaging or self-directed scope expansion.
- No assumption that every provider exposes an API, webhook or background agent on the user's plan.
- No new always-on server, queue database, paid subscription or metered API by default.
- No claim that an agent is running unless supported execution has actually started and its status is observable.

## 3. Architecture at a glance

~~~mermaid
flowchart TB
  OWNER[Project owner: priorities and approvals]
  COORD[Coordinator / Technical CTO: plan, dispatch, reconcile, unblock]
  GH[GitHub control plane: Issues, labels, comments, branches, PRs]
  QUEUE[Task queue and dependency graph: READY / IN PROGRESS / BLOCKED / IN REVIEW / DONE]
  DISPATCH[Dispatcher: manual first; event-driven automation later]
  ADAPTERS[Agent adapters: verified provider integrations only]
  A[Research and audit agents]
  B[Implementation agents]
  C[Security and review agents]
  D[QA and test agents]
  CI[GitHub Actions: builds, tests, security checks]
  REVIEW[Independent review and integration]
  RELEASE[Owner-approved merge and release]

  OWNER --> COORD
  COORD <--> GH
  GH <--> QUEUE
  QUEUE --> DISPATCH
  DISPATCH --> ADAPTERS
  ADAPTERS --> A
  ADAPTERS --> B
  ADAPTERS --> C
  ADAPTERS --> D
  A --> GH
  B --> GH
  C --> GH
  D --> GH
  GH --> CI
  CI --> REVIEW
  REVIEW --> OWNER
  OWNER --> RELEASE
~~~

### Component responsibilities

| Component | Responsibility | Initial implementation |
|---|---|---|
| Owner | Priorities, acceptance, access, paid usage, merge and release decisions | Human decision through GitHub/mobile |
| Coordinator | Decompose work, select agents, manage dependencies, reconcile evidence and keep queue moving | ChatGPT plus documented procedure |
| Control plane | Shared state, history, decisions, artefacts and audit trail | Existing GitHub repository |
| Queue | Ready work, active work, blockers and dependencies | GitHub Issues, labels and issue links |
| Dispatcher | Select a ready task and route it to an eligible agent | Manual assignment first; Actions later |
| Agent adapter | Translate standard task packet to provider invocation and collect results | Add only after provider capability is verified |
| Worker/agent | Research, audit, implement, test or review within scope | Codex/Jules/Copilot/Claude/etc. as individually verified |
| CI | Repeatable checks on exact commits | Existing GitHub Actions |
| Integration/review | Resolve conflicts, check complete diff and acceptance | Coordinator plus independent reviewer |
| Approval gate | Prevent unapproved merge/release | Human owner; repository protections where configured |

## 4. Shared task lifecycle and state model

Every unit of work has one canonical GitHub Issue (or clearly linked sub-issue).

| State | Meaning | Entry condition | Exit condition |
|---|---|---|---|
| READY | Fully scoped and eligible to start | Owner, scope, acceptance criteria and dependencies known | Assigned to an agent or human |
| IN PROGRESS | Real execution has started | Agent/tool accepted or human explicitly started | Evidence submitted, blocked or failed |
| BLOCKED | Cannot safely proceed | Missing dependency, permission, decision, evidence or provider capability | Blocker resolved and readiness revalidated |
| IN REVIEW | Work product is available for review | Findings, diff or test evidence attached | Accepted, changes requested or blocked |
| DONE | Acceptance criteria satisfied and evidence recorded | Review and applicable verification complete | Reopen only for a new defect or changed requirement |

**Assignment is not execution.** Mark IN PROGRESS only after the agent/provider has accepted or execution is demonstrably underway. A timeout or quota error is not completion.

Suggested GitHub labels (create only if absent):
- `agent:ready`, `agent:in-progress`, `agent:blocked`, `agent:review`, `agent:done`
- `type:research`, `type:audit`, `type:implementation`, `type:testing`, `type:security`, `type:documentation`
- `priority:critical`, `priority:high`, `priority:normal`, `priority:low`
- `access:read-only`, `access:write-scoped`, `owner-approval-required`

Labels are a view of state, not a second source of truth. Issue body/comments record details. If GitHub Projects is later selected, it must mirror this state rather than create a conflicting queue.

## 5. Task packet contract

Every dispatch must include:

~~~text
TASK ID / ISSUE URL:
PROJECT / REPOSITORY:
PRIORITY:
TASK TYPE:
OBJECTIVE / USER IMPACT:
PRIMARY AGENT:
APPROVED FALLBACK:
STARTING BRANCH / COMMIT:
DEPENDENCIES:
ALLOWED PATHS:
PROTECTED PATHS / SYSTEMS:
ACCESS MODE: READ-ONLY | WRITE-SCOPED
REQUIRED INPUTS / EVIDENCE:
ACCEPTANCE CRITERIA:
TESTS / VERIFICATION REQUIRED:
EXPECTED OUTPUT:
DEADLINE / NEXT CHECKPOINT (if applicable):
REVIEWER:
NEXT HANDOFF:
OWNER APPROVAL REQUIRED FOR:
~~~

### Mandatory completion / handoff report

~~~text
TASK ID:
AGENT / TOOL / MODEL (if known):
EXECUTION STATUS: ACCEPTED | RUNNING | COMPLETED | FAILED | TIMED OUT
BRANCH / BASE COMMIT:
FILES AND SYSTEMS INSPECTED:
FILES CHANGED:
FINDINGS WITH EVIDENCE:
ACCEPTANCE CRITERIA: PASS | FAIL | NOT VERIFIED
COMMANDS / TESTS ACTUALLY RUN:
EXACT RESULTS / CI RUN / COMMIT:
KNOWN LIMITATIONS / RISKS:
BLOCKERS:
RECOMMENDED NEXT TASK:
NEXT OWNER:
PRODUCTION / DATA / SCHEMA IMPACT:
~~~

Agents must not claim they ran commands, accessed repositories, changed files or completed tests unless they actually did so. The coordinator verifies important claims against GitHub, tool output or CI.

## 6. Continuous parallel execution — no idle-by-default

The coordinator maintains a queue of independently executable tasks. When one task is waiting, it dispatches other READY tasks that do not depend on the pending result.

### Work decomposition
Split large objectives into packages such as:
- root-cause investigation;
- API contract and route inventory;
- test inventory and missing coverage;
- security/dependency audit;
- UI/UX review;
- documentation/acceptance-criteria review;
- bounded implementation;
- regression verification;
- independent code review.

### Dependency graph

~~~mermaid
flowchart TD
  A[Issue triage and scope] --> B[Root-cause investigation]
  A --> C[API contract audit]
  A --> D[Test inventory]
  A --> E[Read-only security review]
  B --> F[Evidence consolidation]
  C --> F
  D --> G[Test plan]
  E --> H[Risk controls]
  F --> I[Implementation brief]
  G --> J[Implementation and tests]
  H --> I
  I --> J
  J --> K[Independent review]
  K --> L[CI verification]
  L --> M[Owner decision]
~~~

Tasks B, C, D and E may run in parallel if scopes are independent. Implementation must not depend on an unfinished root-cause assumption. Test planning and unrelated audits can continue meanwhile.

### Dispatch rules
1. Select the highest-priority READY task whose dependencies are satisfied.
2. Verify agent capability, access, quota and permitted data before dispatch.
3. Assign one accountable owner and one bounded scope per task.
4. Start independent tasks in parallel, subject to concurrency and quota limits.
5. Keep read-only audits parallel when write scopes might conflict.
6. Reserve implementation ownership for disjoint file/path sets.
7. If a task blocks, record the blocker and dispatch the next eligible READY task.
8. When results arrive, validate evidence, update state and dispatch the next dependent task.
9. Do not assign duplicate work just to consume free quota.
10. If there is no safe READY work, state the exact dependency; do not invent tasks.

### Initial concurrency policy
Start conservatively with a maximum of **three concurrent agent executions** across the project. This is a proposed safety limit, not a statement about provider quotas. Increase only after the pilot demonstrates reliable handoffs, low conflict rates and manageable review load. CI jobs may run independently within GitHub's configured limits.

## 7. File ownership, branches and integration

- One implementation task has one accountable author.
- Each write task has explicit allowed-path and protected-path lists.
- Different agents must not edit the same file concurrently.
- If tasks share a file, sequence them or assign one author and make the other agent a read-only reviewer.
- Each implementation agent works on its own feature branch from the agreed base commit.
- Do not have agents independently push into one shared feature branch.
- Findings-only tasks may use issue comments or a report file; they do not need a code branch.
- Integrate through PRs. Check overlapping diffs, changed files, base commit and dependency order.
- Resolve conflicts deliberately; never blindly accept one agent's version.
- Owner merges. No agent may bypass branch protection or merge its own work.

### Protected project boundaries
All rules in `AGENTS.md`, `CLAUDE.md`, `docs/DATABASE_CHANGE_RULES.md` and `docs/DEVELOPMENT_WORKFLOW.md` remain in force.

- No direct push to main.
- No edits, renames, deletions or reformatting of existing/applied files in `backend/schema/`.
- SQL/schema/runner work follows the designated database-author and owner approval process.
- No production data changes, secret changes, migrations, service changes or deployments without explicit owner approval.
- Preserve backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, existing EC2/Nginx/Gunicorn, Amplify and systemd arrangement unless approved.

## 8. Communication and event flow

GitHub is the shared communication bus; agents do not need to message each other directly.

| Event | Required action |
|---|---|
| Task created | Coordinator adds scope, priority, dependencies and acceptance criteria |
| Agent dispatched | Record agent, access scope, dispatch method and timestamp in issue |
| Agent accepts | Set IN PROGRESS and record provider task/run reference if available |
| Agent asks a question | Add question to issue; coordinator/owner answers there |
| Agent reports findings | Add structured evidence and link relevant files/commits |
| Agent completes code | Open/update PR and attach handoff report |
| CI starts/completes | Link workflow run; record exact commit and result |
| Review finds issue | Set changes requested or BLOCKED; create bounded follow-up |
| Quota/provider failure | Record failure and route to approved fallback from last checkpoint |
| Owner decision | Record approval/rejection and scope in issue/PR |

Do not copy private conversation transcripts wholesale. Transfer only minimum task context, relevant excerpts, non-sensitive evidence and decisions. Never post credentials, customer/payment data or production secrets in an issue or agent prompt.

## 9. Dispatcher and automation design

### Phase 0 — documented/manual dispatch
Use GitHub Issues, comments, labels, branches and PRs. The coordinator assigns work manually and verifies each acceptance/handoff. This mode requires no provider API keys or additional infrastructure.

### Phase 1 — GitHub-native workflow automation
Initial repository automation is staged in PR #177 (not active on main until the owner merges it):
- `.github/workflows/agent-task-governance.yml` validates agent-task issue forms on open/edit/reopen/label events, creates five status labels, marks complete tasks READY and marks incomplete tasks BLOCKED.
- `.github/scripts/validate_agent_issue_template.py` checks the issue-form YAML structure and required field IDs.
- `.github/workflows/ci.yml` runs the issue-template validator on pull requests.
- This workflow does **not** start or dispatch an external agent. IN PROGRESS, REVIEW and DONE remain explicit execution/review states, not automatic assumptions.

After the manual pilot is stable, add GitHub Actions for deterministic operations:
- validate required task fields and labels;
- check owner, acceptance criteria and dependency declaration;
- validate handoff/checklist metadata;
- run existing lint, tests, builds and security checks;
- post CI result links and commit SHAs;
- notify/label on PR and workflow state changes where permissions allow.

Use event-driven triggers such as issue labels, issue edits, PR events and `workflow_dispatch`. Avoid always-running polling loops. Actions must not invoke external agents until the relevant adapter has been approved and tested.

### Phase 2 — first provider adapter
Integrate **one** provider at a time. The adapter must support, or explicitly document the absence of:
1. task submission with a stable task/run identifier;
2. scoped repository and branch access;
3. status retrieval or completion notification;
4. structured result/handoff capture;
5. cancellation or timeout handling;
6. quota/error visibility;
7. least-privilege credential management;
8. safe failure and retry semantics.

If a provider only supports manual use in its app, keep it as a human-dispatched agent and record its handoff in GitHub. Do not simulate an API or claim automatic dispatch.

### Phase 3 — multi-agent dispatch
After one adapter works end-to-end, add more adapters behind the same task contract. Select providers based on role, access, availability, quota and task type. Fallback resumes from the prior checkpoint and must not duplicate an already-running write task.

### Phase 4 — metrics and optimisation
Only after queue/event records are reliable, track cycle time, time blocked, completion rate, CI failure rate, rework, merge conflicts, fallback frequency, quota consumption and review latency. Do not optimise for number of agents or commits.

## 10. Failure, timeout and fallback handling

| Failure | Response |
|---|---|
| Agent does not accept task | Keep READY or mark BLOCKED with provider reason; dispatch eligible fallback |
| Agent times out | Record last checkpoint; verify no active duplicate run before retry |
| Provider quota exhausted | Stop new work on provider; use assigned KEEP fallback |
| Repository permission denied | Do not broaden permissions automatically; ask owner or use read-only/manual path |
| Conflicting findings | Ask for source evidence; coordinator records decision and rationale |
| Overlapping edits | Stop one writer, preserve both branches, compare diffs and select one integration owner |
| CI fails | Route failure to implementation owner; do not mark DONE |
| Secret or sensitive data exposed | Stop task, notify owner, follow incident process; do not copy secret into logs |
| No independent READY work | State the dependency and wait; no artificial work |

Retries must be idempotent where possible. Before retrying a write task, check provider status, branch and commit to avoid duplicate changes.

## 11. Security, permissions and data handling

- Default to read-only access for research and review agents.
- Grant write access only for a specific issue, branch and file scope.
- Use separate provider credentials/adapters; never share personal login passwords or session cookies.
- Store approved tokens only in GitHub Actions secrets or the provider's approved secret store. Never commit tokens or paste them into issue bodies.
- Prefer short-lived, narrowly scoped credentials. Document scopes, expiry and rotation owner.
- Do not send production secrets, .env values, customer personal data, payment data or sensitive financial records to external agents.
- Use sanitised fixtures and disposable CI databases for tests.
- Require owner approval before enabling paid APIs, metered usage, new apps, new permissions or external data transfer.
- Log task IDs, provider run IDs, repository, branch, commit, status and non-sensitive outcomes. Never log secret values.
- Keep owner approval as a hard gate for merge, production database operations, infrastructure changes and deployment.

## 12. Mobile-first operating experience

The owner should be able to use GitHub mobile or a mobile browser to:
- see READY/IN PROGRESS/BLOCKED/IN REVIEW/DONE work;
- open a task and read scope and evidence;
- review agent questions and handoffs;
- inspect branches, PR diffs and Actions results;
- approve or reject a task/PR;
- see why a task is blocked and who owns the next action.

Test mobile access for each provider workflow. An app that only shows notifications/comments is companion access, not full execution. Cloud work is mobile-operable only if it can be dispatched/monitored and its output reviewed from mobile.

## 13. Observability and operational dashboard

The first dashboard is GitHub Issues/labels and Actions; do not create a new dashboard application for the pilot.

Track:
- counts of READY, IN PROGRESS, BLOCKED, IN REVIEW and DONE;
- active agent/provider and task ID;
- oldest blocked task and exact blocker;
- current PR and CI state;
- tasks waiting for owner decision;
- provider quota/permission status where known;
- last successful handoff and last queue review.

A task board is a view of GitHub data, not a separate source of truth.

## 14. Rollout plan and exit criteria

| Stage | Deliverable | Exit criteria | Agent integration? |
|---|---|---|---|
| A. Architecture and documentation | Blueprint, collaboration protocol, development workflow and task template | Owner understands lifecycle, roles, dependencies and safety | No |
| B. Manual pilot | Issue templates, labels, structured handoffs and parallel read-only audits | One small batch completes with evidence and no overlapping writes | No automatic provider calls |
| C. GitHub-native automation | Validations and CI/notification workflows | Workflow tested on sample issue/PR; permissions and failure behaviour verified | No external agent dispatch |
| D. First provider | One verified provider adapter | Submit → execute → report → timeout/fallback tested end-to-end | One |
| E. Additional providers | Reusable adapters and routing | Each provider passes capability, permission, quota and failure tests | One by one |
| F. Optimisation | Queue metrics and operational reporting | Reliable state and handoffs over multiple work cycles | As approved |

### Stage A completion checklist
- [ ] Architecture and component boundaries documented.
- [ ] Task lifecycle and state definitions documented.
- [ ] Parallel work and dependency rules documented.
- [ ] Task packet and handoff report standardised.
- [ ] Branch/file ownership and integration rules documented.
- [ ] Security, access and owner approval gates documented.
- [ ] Failure, timeout and quota fallback behaviour documented.
- [ ] Mobile-first control requirements documented.
- [ ] Manual-first staged rollout documented.
- [ ] GitHub issue template added and reviewed.
- [ ] Cross-links added to contributor and development instructions.
- [ ] No external agent adapter, paid API or production integration enabled in Stage A.

## 15. Decisions required before implementation

These are explicit approval gates, not assumptions:
1. Confirm initial concurrency limit (proposed: three concurrent agent executions).
2. Confirm GitHub Issues and labels as the canonical task queue for the pilot.
3. Confirm the first provider to integrate after the manual pilot and verify actual account entitlement.
4. Approve any GitHub Actions permission expansion or provider API secret.
5. Approve paid/metered usage, new external service or production access separately.

## 16. Definition of done for the orchestration foundation

The foundation is ready for the first agent integration only when the Stage A checklist is complete, the owner has reviewed the design, issue/handoff templates are present, contributor docs point to this blueprint, and the team can complete a manual multi-task pilot without overlapping writes or losing evidence.

**This document describes the target architecture. It does not claim that a dispatcher, provider adapters, scheduled agent runs or automatic task routing are already installed.**
