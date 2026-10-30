# Development, GitHub and Operations Workflow

> **Purpose:** One operational guide for choosing the right tool, diagnosing the right layer, managing pull requests and verifying releases. The README is the overview; this document is the detailed workflow. For MUST KEEP primary tools, KEEP fallbacks, free-quota switching and mobile-first access, follow [Tool Utilisation Policy](TOOL_UTILISATION_POLICY.md).

## 1. Tool register

| Tool / service | Primary responsibility | Use it for | Not a substitute for |
|---|---|---|---|
| GitHub | Source of truth | Branches, commits, PRs, reviews, Actions, repository history | Running or debugging the live application |
| GitHub Codespaces | Optional computer-based development workspace; not required in the current mobile-first phase | Read/edit source, reproduce bugs, run tests/builds, inspect dependencies and local logs when a computer workflow is available | Mobile-first task execution or production runtime verification |
| Swagger / OpenAPI | API contract and interactive endpoint testing | Routes, schemas, auth, request/response, status codes and reproducible API tests | Frontend rendering or production infrastructure diagnosis |
| ChatGPT | Technical lead and coordinator | Planning, architecture, analysis, review, documentation and evidence-based decisions | Executing a test unless a runner/tool actually ran it |
| Claude | Designated database/SQL/runner author by current project policy | Scoped schema, migration runner and database review work | Owner approval or live production authorization |
| GitHub Copilot | Additional AI coding assistant; capabilities depend on the assigned plan | Code completion, explanations, bounded implementation, test suggestions and first-pass review where enabled | Human review, required CI, repository safety rules, database authorisation or owner approval |
| GitHub Actions | Automated CI | Backend tests, frontend builds, schema tests and PR quality gates | Production DB checks or post-deployment E2E verification |
| AWS EC2 | Backend host | Runtime, OS, process, networking, disk, logs and environment investigation | Source-code development |
| AWS Systems Manager Run Command | Remote EC2 operations | Approved read-only diagnostics and explicitly approved commands | An unrestricted substitute for review/approval |
| AWS Amplify | Frontend hosting/build | Build logs, deploy status, hosting and frontend release checks | Backend API or database diagnosis |
| PostgreSQL | Persistent data store | SQL, schema, constraints, transaction and integrity inspection | A place for unreviewed manual production fixes |
| Nginx | Reverse proxy | HTTPS, host routing, upstream and proxy diagnostics | FastAPI business logic |
| Gunicorn + FastAPI | Backend application runtime | Process, route registration, middleware and application behaviour | Frontend build/hosting |
| systemd service/timer | Existing process and scheduled operations | Service state, timer schedule, execution status and journal logs | A reason to change the cadence or replace automation |

Only list additional products as active integrations after verifying their actual repository configuration, workflow or deployed connection. A product discussed during planning is not automatically an implemented dependency.

## 2. Diagnostic order and decision matrix

Use the following order for normal development. Follow the evidence: skip directly to the relevant layer during a confirmed incident, outage or security event.

| Problem | First tool | Inspect | Escalate to |
|---|---|---|---|
| Page, layout, React state, form or browser error | Mobile browser + GitHub issue/PR evidence; assign a scoped Codex/Jules/Copilot task where code changes are needed | Reproduce the visible issue, capture route/steps/screenshots and inspect CI/browser evidence | Swagger if API contract is implicated; optional Codespaces when computer access resumes |
| API route missing / wrong payload / 401 / 403 / 404 / 422 | Swagger / OpenAPI | Route, schema, auth, headers, request, response and status | Assign a scoped cloud coding-agent task through mobile-accessible workflow; optional Codespaces when available |
| API 500 or timeout | Swagger first | Reproduce request, response body, request ID if available | GitHub Actions/log evidence and a scoped cloud coding-agent task; AWS only if runtime evidence points there |
| Database undefined table/column/constraint | Swagger/API evidence and GitHub source/docs review; follow database-owner process | SQL migration, query, model and required-schema manifest | Claude as designated database author under CLAUDE.md; read-only DB inspection by authorized owner if environment state matters |
| Migration test failure | GitHub Actions | Exact failing job/step and commit | Reproduce against disposable PostgreSQL 15/16 in an approved runner/workspace; Codespaces only when available |
| Backend service down / process crash / port unreachable | AWS EC2 or SSM | systemd, Gunicorn, Nginx, logs, port 8001, host health | Infrastructure owner |
| Frontend deployment/build issue | GitHub Actions then Amplify | Build command, artifact, environment configuration, deploy state | Scoped cloud coding-agent task; Codespaces only when available |
| Timer or scheduled synchronization issue | AWS EC2 / systemd | Timer status, last/next trigger, service result and journal | Operations owner |
| Production ledger/checksum mismatch | Owner-only database preflight | Live ledger, file checksums, target DB and backup readiness | Database owner; stop release until reconciled |

### Normal diagnostic sequence

```mermaid
flowchart TD
  ISSUE[Reported defect] --> GH[GitHub: branch, commit, PR and CI]
  GH --> CODE[Codespaces: reproduce and inspect source]
  CODE --> API{API contract involved?}
  API -->|Yes| SW[Swagger / OpenAPI: inspect and test]
  API -->|No| TEST[Local tests and build]
  SW --> TEST
  TEST --> CI[GitHub Actions]
  CI --> INFRA{Evidence of runtime / hosting issue?}
  INFRA -->|No| FIX[Fix at source layer and retest]
  INFRA -->|Yes| AWS[AWS EC2 / SSM or Amplify]
  AWS --> VERIFY[Verify runtime and user journey]
  FIX --> PR[PR review and owner merge]
  VERIFY --> PR
```

Do not use AWS as the first debugging destination for ordinary source, UI or API contract defects. Do not use a green CI result to claim production health.

## 3. GitHub branch and pull-request lifecycle

### Required flow

1. Fetch latest `main` and create a focused feature branch from it.
2. Read README, AGENTS and the relevant canonical technical documents.
3. Implement only the agreed scope; preserve unrelated working code.
4. Run relevant local checks in Codespaces.
5. Update relevant docs and add a dated entry to `IMPORTANT_UPDATES.md` for major changes.
6. Open/update the PR using the repository template.
7. Review the complete diff, schema impact, docs impact and CI evidence.
8. Address review comments and keep the branch current with `main`.
9. Repository owner merges only when required checks and review conditions are met.
10. Deployment is a separate, explicitly approved action; record post-deployment verification.

### PR operating policy

| Control | Policy |
|---|---|
| Open PR portfolio | Normal operating ceiling: **15 open PRs** |
| Resolution target | **5 calendar days** from opening |
| Escalation | Review blocker/owner/next action by Day 7 |
| Maximum target window | Resolve by **Day 10** through merge or closure with a reason |
| Required ownership | Every PR has an accountable owner and clear scope |
| Required quality | Acceptance criteria, tests, documentation impact and CI evidence |
| Stale / blocked PR | State blocker, responsible person and next review date |
| Urgent exception | Security/production incident PRs may exceed the cap with owner visibility |

These are operating targets, not automatic GitHub enforcement. Unless an approved GitHub App or scheduled automation is configured, the repository does not automatically count open PRs or close aged PRs.

**No metric-driven unsafe merge:** Never merge merely to meet the five/ten-day target. Never close valid work just to reduce the count. If work cannot safely merge, keep it blocked with a documented owner and next review date, and escalate the portfolio exception.

### PR state vocabulary

Draft → Ready for review → In review → Changes requested / Blocked → Approved → Merged or Closed.

A closed PR must have a short reason (superseded, duplicate, no longer required, unsafe, abandoned with owner decision, etc.). Merged means integrated into the target branch; it does not mean deployed.

## 4. AI team collaboration and delegation

Use [AI Team Collaboration & Delivery Policy](AI_TEAM_COLLABORATION.md) as the canonical source for contributor roles, file ownership, batch sizing, handoffs, review and stop conditions. Use [Tool Utilisation Policy](TOOL_UTILISATION_POLICY.md) for MUST KEEP primary tools, KEEP fallbacks, free-quota switching and mobile-first capability. The policy treats the owner as final decision-maker and ChatGPT as coordinator; Claude, Copilot, Perplexity and Gemini have distinct, bounded responsibilities. GitHub issues, branches, PRs and Actions are the shared project record; separate AI chat sessions do not communicate directly.

Keep Claude and Copilot implementation batches to 2–3 related files where practical, assign non-overlapping file sets, and start the next batch only after the prior batch is reviewed. Use two focused work windows per day separated by roughly 3–4 hours when practical; this is a planning preference, not an automatic background schedule. Perplexity starts read-only until repository access is verified. Gemini reviews only the exact excerpts, diffs or screenshots supplied. Verify actual plan, permissions and repository coverage before relying on any agent feature.

GitHub Copilot remains an additional coding assistant, not a replacement for the owner, technical lead, designated database author, CI or human review. Its actual plan and enabled capabilities must be checked in the account; repository integration alone does not prove paid access, cloud-agent eligibility or unlimited usage. See [GitHub Copilot plans, limits and repository policy](GITHUB_COPILOT.md). All contributors must follow `AGENTS.md`, work on feature branches, preserve protected files and provide exact test/CI evidence. No agent may merge, bypass branch protection, deploy, change production data/secrets/infrastructure, or take over protected SQL/migration authorship.

## 5. Mobile-first development and review

For the current phase, use mobile-accessible GitHub and approved cloud-agent workflows as the default operating path:

- inspect repository files, issues, branches, PRs, checks and commit history through GitHub;
- assign scoped implementation tasks to Codex first, then Jules or Copilot when quota/capability requires a fallback;
- use Claude for complex reasoning, designated database-author work under CLAUDE.md, and independent review;
- use Gemini and Perplexity for bounded review and research, with access verified before relying on private repository coverage;
- run backend tests, frontend builds and browser regression tests through existing GitHub Actions where configured;
- use Swagger/OpenAPI and Hoppscotch for API inspection and testing;
- review exact diffs, test results and CI evidence before owner approval.

Codespaces remains an optional development workspace when computer access is available; it is not a prerequisite for the current mobile-first workflow. Never point a local test at production credentials or database. Keep secrets out of terminal output and screenshots.

## 6. Swagger / OpenAPI: primary use

Use Swagger first for API-specific defects:

- confirm the expected route is registered;
- inspect method, path, parameters, request body and response schema;
- authenticate with the correct staff/customer token type;
- test status codes, validation errors and permissions;
- capture reproducible request/response evidence.

Swagger is commonly available at the FastAPI OpenAPI UI path (for example `/docs`) on the configured backend host. Confirm the deployed URL and environment rather than assuming a URL. A successful Swagger request proves only that specific request in that environment; it does not prove the frontend journey or all roles.

## 7. AWS: when and how to use it

Use AWS only when evidence indicates server, runtime, networking, environment, hosting, deployment or production database concerns.

### EC2 / Systems Manager Run Command

Appropriate checks include:

- systemd service and timer status;
- Gunicorn process and listener on `127.0.0.1:8001`;
- Nginx service and upstream/proxy logs;
- backend application logs and recent deployment commit;
- disk, memory, CPU, connectivity and TLS/networking;
- approved read-only PostgreSQL checks.

Run Command is for controlled remote execution. Prefer read-only commands first. Destructive commands, service changes, migration application, secret changes and deployment require explicit owner authorization and a reviewed plan.

### AWS Amplify

Use Amplify for frontend build/deploy state, build logs, hosting configuration and the deployed frontend. If the build fails, inspect the exact failed command and dependency/build output; reproduce in Codespaces where possible before changing configuration.

### Fixed runtime constraints

- EC2 backend behind existing Nginx and Gunicorn.
- Backend listener: `127.0.0.1:8001`.
- PostgreSQL: `5432`; production database name: `sb_app`.
- Existing systemd service/timer and synchronization flow must be preserved.
- Existing Amplify frontend hosting must be preserved.
- Public API prefix remains `/api`.

Do not change these targets as a workaround. Verify the real environment before any operation.

## 8. Release and verification gates

| Gate | Evidence required |
|---|---|
| Source complete | Diff reviewed; acceptance criteria addressed |
| Local verification | Exact commands and results recorded |
| CI verified | Required GitHub Actions checks green on exact commit |
| PR approved | Review complete; branch current; owner approval |
| Merged | GitHub confirms merge SHA |
| Deployment approved | Owner authorization and release plan |
| Deployed | Environment and deployed commit recorded |
| Post-deploy verified | Health, logs and relevant end-to-end journeys passed |

For schema releases, follow `docs/DATABASE_CHANGE_RULES.md`; the production preflight and live migration runner are owner-controlled. CI never substitutes for live ledger and backup checks.
