# Free-First Tool Utilisation & Role Assignment Policy

> Status: Proposed repository operating policy — 31 October 2026  
> Applies to: Superbajaar, Financial OS, KPMC and shared research/development workflows.  
> Operating model: Mobile-first and browser-accessible. Desktop-dependent workflows are not active in this phase.

## 1. Purpose and non-negotiable rules

This document assigns one clear job to every approved tool and defines which tool to use first and where to switch when a free allowance is exhausted.

1. MUST KEEP means primary: start with this tool for its assigned responsibility.
2. KEEP means approved fallback or specialist: switch when the primary reaches its free limit, is unavailable, or cannot perform the required task.
3. Do not purchase a subscription or enable metered billing merely because a primary quota is exhausted. Try the approved free fallback first.
4. Do not run the same task through multiple agents just to consume free quotas. Every tool must have a distinct job.
5. Active workflows must be usable through an Android/iOS app or mobile browser, or run in an already-approved cloud CI/automation service controllable from mobile.
6. A mobile app that only previews, comments or monitors does not qualify as a full editor. Record companion-only access honestly.
7. Free software does not mean free model inference, hosting, storage, API calls or compute. Check all cost layers.
8. Do not paste secrets, production credentials, private customer/payment data or sensitive financial/business records into an AI or third-party service unless the owner has approved its access and data handling.
9. GitHub and canonical project documents are the shared source of truth. Chat histories are not the project record.
10. No new repository, database, cloud server or paid integration may be introduced as an ordinary tool-selection workaround.

## 2. Priority definitions

| Label | Meaning | Rule |
|---|---|---|
| MUST KEEP | Primary tool or essential foundation | Use first and preserve its assigned role |
| KEEP | Free fallback or specialist | Use when primary is limited, unavailable or unsuitable, or for a distinct specialist task |
| OPTIONAL / NOT ACTIVE | Overlapping, desktop-dependent, setup-heavy or unnecessary now | Do not introduce without a documented reason and owner approval |

A tool can be open-source and still be KEEP if another tool is the better primary. A quota-based tool can be MUST KEEP if it is the strongest primary; switch to KEEP when its allowance is exhausted.

## 3. Team roles

| Role | Responsibility | Boundaries |
|---|---|---|
| Project owner (human) | Product priorities, business decisions, data/privacy approval, paid-plan approval, merge and production-release approval | Retains final authority |
| ChatGPT — Technical CTO / coordinator | Architecture, planning, task decomposition, cross-agent coordination, technical review, evidence checks, documentation and this tool policy | Must not claim unexecuted work or approve production changes |
| Claude — implementation partner / independent reviewer | Complex reasoning, bounded code implementation and review; database work only under the designated database-author process | Cannot bypass database rules, owner approval or verification |
| Gemini — independent reviewer / Google-workflow assistant | Review supplied diffs, screenshots, documents and architecture; Google ecosystem and document analysis | Do not assume private repository access |
| Perplexity — research specialist | Source-backed web research, pricing verification, competitor and market research | Read-only by default; search results are not implementation evidence |
| GitHub — shared project record | Repository, issues, branches, PRs, reviews, Actions and audit trail | Does not prove live application health |
| Codex / Jules / Copilot agents | Scoped repository tasks with assigned paths and acceptance criteria | No concurrent overlapping edits, merge, deployment or production data changes |
| Codespaces | Development workspace for source inspection/editing and tests when that workflow is available | Not a requirement for the current mobile-first operating phase |

ChatGPT coordinates work and maintains the operating record. It does not pretend to execute work in tools that have not been connected or invoked.

## 4. Approved tool register and fallback order

### 4.1 AI assistants and research

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | ChatGPT | Technical CTO, architecture, planning, coordination, finance/business reasoning and documentation | Gemini or Claude for a specific task; Perplexity for cited web research |
| MUST KEEP | Gemini | General research, Google ecosystem, document analysis and independent review | Claude for deep reasoning; Perplexity for sourced web research |
| MUST KEEP | Perplexity | Current web research, pricing, competitors and source verification | Gemini or ChatGPT web research when its free search allowance is exhausted |
| KEEP | Claude | Complex code review, long-form reasoning and scoped implementation through supported mobile/browser workflows | Codex, Jules or Copilot for repository-agent tasks; do not assume Claude Code terminal workflows are mobile-capable |
| KEEP | DeepSeek | Additional reasoning or second opinion | Gemini or ChatGPT |

### 4.2 Coding and repository agents

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Superpowers | Development workflow: clarify, plan, TDD, debug systematically, review and verify | Use with an available compatible AI agent; Superpowers is a skills/workflow layer, not a model |
| MUST KEEP | GitHub | Source of truth, issues, branches, PRs, reviews and CI visibility | No substitute; all agents report work back here |
| MUST KEEP | OpenAI Codex | Primary delegated coding agent for scoped repository tasks where the account's mobile/cloud workflow supports the task | Jules or Copilot when Codex quota/feature is unavailable |
| KEEP | Google Jules | Asynchronous GitHub coding tasks and bounded implementation | Codex or Copilot |
| KEEP | GitHub Copilot | Code explanations, coding assistance, bounded agent tasks and PR assistance where the actual plan enables them | Jules or Codex |
| KEEP | Amazon Q Developer | AWS-specific investigation and cloud guidance through supported mobile/browser access | Gemini/ChatGPT for explanations; approved AWS console/SSM for verified operations |
| KEEP | OpenHands | Open-source autonomous coding only if a supported hosted/mobile-accessible deployment already exists | Codex/Jules; do not create a new server or incur compute/model costs just to activate it |

NOT ACTIVE in the mobile-first phase: Cline, Aider, OpenCode and local terminal-centric agent workflows whose useful operation depends on a desktop IDE/terminal. Reconsider when desktop development resumes.

### 4.3 Code quality, security and testing

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | GitHub Actions | Repeatable backend/frontend tests, builds and PR quality gates | If quota is exhausted, use an already-approved runner and record the CI gap; do not silently add paid runners |
| MUST KEEP | Dependabot | Dependency alerts and update PRs | Manual GitHub dependency/security review |
| MUST KEEP | Gitleaks | Secret detection in commits and repository history through CI | GitHub secret scanning where available |
| MUST KEEP | Playwright | Automated browser journeys and regression tests through existing CI | Manual mobile-browser checks only as supplemental evidence |
| KEEP | Semgrep | Additional static security analysis | Dependabot, Gitleaks and code review |
| KEEP | SonarQube Cloud | Maintainability, bugs and code-quality analysis when private-repository eligibility is confirmed | Semgrep and CI; never make a private repository public for a free scan |
| KEEP | Snyk | Specialist dependency/code/container vulnerability checks | Semgrep, Dependabot and Trivy where appropriate |

### 4.4 API testing and technical documentation

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Swagger / OpenAPI | First stop for FastAPI route, schema, authentication, payload and status-code diagnosis | Hoppscotch for additional requests; Swagger remains the API contract |
| MUST KEEP | Hoppscotch | Mobile-browser API requests, collections and reproducible endpoint tests | Postman if a required feature is unavailable |
| KEEP | Context7 | Current framework/library documentation lookup | Official docs and Gemini/Perplexity research |
| KEEP | Firecrawl | Website extraction for research and data gathering | Perplexity or direct public pages |
| KEEP | Postman | Alternative API client and team collection workflow | Prefer Hoppscotch for routine free usage |

### 4.5 UI/UX and frontend

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Figma | Design source, UI review, prototypes, comments and design-system reference using supported mobile/browser capabilities | Penpot if a Figma limit blocks the task; advanced editing may need a larger screen |
| KEEP | MagicPath | Generate interface concepts and draft React UI ideas | Figma and Gemini for design/review |
| KEEP | Penpot | Open-source design alternative | Figma when a required integration is unavailable |
| KEEP | Lighthouse | Performance, accessibility and SEO audits through an existing browser/CI workflow | PageSpeed Insights or browser performance reports |
| KEEP | Lovable (existing SuperBajaar Connect project) | Isolated UI concepts, design critique and read-only frontend compatibility audits only until repository binding and framework compatibility are verified | Figma/Gemini for design review; canonical implementation remains in the Superbajaar GitHub repository |

Lovable is not a canonical code source until its exact repository/branch binding is verified. Do not use its separate project to edit or deploy the production application; see [Agent Integration Readiness](AGENT_INTEGRATION_READINESS.md).

Storybook is not an active mobile-first requirement because authoring/running component environments depends on the development workflow. Use a deployed preview only when one already exists.

### 4.6 Finance, investment and analytics

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Google Sheets | Budgets, forecasts, financial models, reconciliations and operating trackers | Approved spreadsheet workflow; CSV exchange when needed |
| MUST KEEP | Metabase Open Source | Business, sales, inventory and Financial OS dashboards on existing approved hosting | Sheets for small analyses; never expose production data |
| MUST KEEP | OpenBB | Investment and market research subject to provider licensing and freshness checks | Official NSE/BSE/broker sources and approved data providers; never silently substitute delayed data for live prices |
| KEEP | Deepnote | Hosted notebook analysis within its free quotas | Google Sheets for lighter analysis |
| KEEP | Grafana OSS | Infrastructure and application monitoring through an existing instance | AWS/host monitoring and logs |
| KEEP | Google Analytics 4 | Website acquisition and customer behaviour analytics | PostHog for product-specific events |
| KEEP | Google Search Console | Indexing, search queries and SEO health | Ahrefs Free for supplementary SEO research |
| KEEP | PostHog | Product analytics, funnels, session recordings and feature flags within free quotas | GA4 for broad web analytics |
| KEEP | Ahrefs Free | SEO, backlinks and competitor research | Search Console for first-party search data |

Python/Pandas/Jupyter remain valid technologies in the Financial OS codebase, but are not listed as mobile-operated applications. Do not require a desktop notebook workflow during this phase.

### 4.7 Business operations and automation

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Odoo (existing deployment) | ERP, accounting, inventory, procurement, POS, CRM and business operations | Existing approved operational process; do not assume Odoo One App Free covers a multi-app ERP |
| MUST KEEP | Linear | Development backlog, ownership, priorities and issue tracking if the free workspace is sufficient | GitHub Issues; avoid duplicating every task in both |
| MUST KEEP | Notion | Business knowledge base, SOPs, strategy and non-code documentation | Repository Markdown for technical canonical docs |
| MUST KEEP | n8n Community Edition (existing/approved hosting only) | Reusable business and technical workflow automation | Activepieces Cloud Free within its daily credits |
| KEEP | Activepieces Cloud Free | Hosted automations within daily credit allowance | n8n when the approved instance is available |
| KEEP | Airtable | Small operational datasets and lightweight workflows within record/API limits | Odoo for transactional records; Sheets for simple tables |

### 4.8 E-commerce and marketing

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Google Analytics 4 | Website acquisition and customer behaviour | PostHog for product journeys |
| MUST KEEP | Google Search Console | Organic search visibility and indexing | Ahrefs Free for supplementary competitor/backlink checks |
| MUST KEEP | Meta Business Suite | Organic Facebook/Instagram publishing and inbox operations | Native social app for urgent manual actions |
| KEEP | PostHog | Product journeys, conversion funnels and feature adoption | GA4 for broad traffic and acquisition |
| KEEP | Ahrefs Free | SEO and competitor research | Search Console for first-party performance |
| NOT ACTIVE | Shopify | Paid store platform overlaps with the existing custom Superbajaar commerce platform | Reconsider only with a separate business case |

### 4.9 AI model and developer infrastructure

| Priority | Tool | Assigned job | Fallback |
|---|---|---|---|
| MUST KEEP | Google AI Studio | Prototype Gemini prompts and API behaviour within eligible free-model limits | OpenRouter free models after checking privacy and quota |
| KEEP | Hugging Face | Explore open models, datasets and hosted demos | AI Studio or OpenRouter |
| KEEP | OpenRouter | Test eligible free models from multiple providers | AI Studio or a provider's direct free plan |
| NOT ACTIVE | Ollama | Local model runtime | Requires suitable local computer hardware; excluded from mobile-first phase |

## 5. Quota exhaustion and fallback procedure

1. Check the primary tool's account usage/remaining quota before a large task.
2. If sufficient, use the MUST KEEP tool for its assigned job.
3. If exhausted or the required feature is unavailable, record the tool, feature, date and remaining allowance if shown.
4. Select the KEEP fallback assigned in the register. Transfer only the task brief, relevant non-sensitive context, paths, acceptance criteria and prior evidence.
5. Continue from the last verified checkpoint. Do not restart the entire task without reason.
6. If the fallback cannot perform the task, use another approved specialist or ask the owner. Do not silently enable paid usage or create a new account/service.
7. Record the outcome in the GitHub issue/PR or relevant operating log.

Examples:
- Coding: Codex first; Jules or Copilot when Codex is limited; Claude may independently review the resulting diff.
- Research: Perplexity first for cited web research; Gemini or ChatGPT web research when its allowance is exhausted.
- API: Swagger/OpenAPI first for contract diagnosis; Hoppscotch for mobile-browser requests; Postman only for a feature Hoppscotch lacks.
- Automation: existing approved n8n first; Activepieces Cloud Free only within its daily allowance. No new server or paid execution without approval.

## 6. Required task allocation and handoff

Before work begins, the coordinator must provide: task/issue ID; objective; primary tool/agent; fallback; repository/branch/base commit; allowed paths and protected files; acceptance criteria; verification commands; data/access boundary; reviewer and next owner.

Every completion report must state:

    Task / Issue:
    Assigned role and tool:
    Primary or fallback:
    Reason for selection / quota status:
    Repository and branch:
    Files inspected:
    Files changed:
    Acceptance criteria: PASS / FAIL / NOT VERIFIED
    Commands and checks actually run:
    Exact result / CI run / commit:
    Known limitations:
    Next reviewer / owner:
    Production or deployment impact:

No contributor may report a check as passed unless it actually ran. A suggestion, generated test, screenshot or code review is not proof of a passing test.

### 6.1 Continuous work and parallel execution (no idle-by-default rule)

The coordinator must keep the project moving while an agent, tool, CI run or external service is processing a task. Waiting for one result is not a reason for the rest of the team to sit idle.

**Operating rules**

1. Maintain a prioritised work queue with these states: READY, IN PROGRESS, BLOCKED, IN REVIEW and DONE. Every active item has an owner, objective, expected output and next handoff.
2. Break large work into small, independently verifiable work packages. Identify dependencies before assigning them.
3. Start all genuinely independent READY work in parallel, subject to tool availability, quota, access permissions and a sensible limit on concurrent work.
4. While one agent investigates or implements, assign other agents work that does not depend on its unfinished result. Examples include a separate module audit, API-contract review, test inventory, security review, documentation audit, UI review or verification of an unrelated completed change.
5. Do not assign speculative implementation that depends on facts still being investigated. Such work remains BLOCKED until the required evidence is recorded.
6. Avoid overlapping write scopes. Each coding task must have a defined branch and allowed file/path scope. Two agents must not edit the same file or shared migration sequence concurrently unless the coordinator has explicitly divided and coordinated the change.
7. Prefer parallel read-only audits, research and test design when write conflicts are possible. Consolidate their findings into one evidence-based implementation brief.
8. When a task becomes BLOCKED, record the exact blocker, what is needed to unblock it, who can provide it and the next review point. Immediately move to another READY task.
9. When a result arrives, the coordinator reviews it, updates the queue and assigns the next dependent task promptly. Do not leave completed work waiting without a reviewer or next owner.
10. Keep CI, builds and long-running checks asynchronous where possible. While they run, continue with independent documentation, test review, risk analysis or other module work; do not claim results until the run finishes.
11. The coordinator continuously checks for available independent work and reprioritises around critical-path dependencies. Priority order is: production/security/data risks; blockers on the critical path; high-impact user-facing defects; remaining module work; cleanup and documentation.
12. Parallelism is not a target by itself. If no safe independent task is READY, explain the dependency and wait for the specific required input rather than inventing work.

**Example: investigation running in parallel**

| Workstream | Owner/tool role | Can proceed while the investigation runs? | Output |
|---|---|---|---|
| Root-cause investigation | Primary coding/review agent | Yes — this is the lead task | Evidence, affected paths and root cause |
| API contract audit | API specialist | Yes, if it can inspect independently | Endpoint/schema discrepancies |
| Test inventory | QA/Playwright or CI owner | Yes | Existing coverage and missing test cases |
| Security review | Security reviewer | Yes, read-only and scoped | Risks and recommended controls |
| Documentation/acceptance review | Coordinator or documentation agent | Yes | Updated acceptance criteria and handoff brief |
| Fix dependent on confirmed root cause | Assigned implementation agent | No, until evidence is available | Scoped fix on its own branch |
| Regression verification | QA/CI owner | After a candidate change exists | Actual test/build results |

**Daily execution loop**

- Plan: rank work, split it into independent packages and identify dependencies.
- Dispatch: assign available agents and tools with explicit scopes and acceptance criteria.
- Execute: keep independent work moving while long-running tasks are underway.
- Integrate: collect findings in GitHub, reconcile contradictions and unblock dependent work.
- Verify: run the relevant tests and checks; record exact evidence.
- Handoff: send completed work to the next owner and immediately refill the READY queue.

The coordinator must never imply that an agent is working in the background unless a task was actually assigned through a supported tool or workflow. If no asynchronous agent execution is available, the coordinator should continue with other work it can genuinely perform and clearly state what remains dependent on an external agent or user action.

## 7. Project safeguards

All tools and agents must follow AGENTS.md, docs/DEVELOPMENT_WORKFLOW.md, docs/AI_TEAM_COLLABORATION.md, docs/DATABASE_CHANGE_RULES.md and CLAUDE.md where applicable.

- Never push directly to main; create a feature branch from latest main. The owner merges.
- Never edit, rename, delete or reformat existing files in backend/schema/.
- For an approved schema change, follow the exact additive, idempotent, uniquely numbered migration rules and designated database-author process.
- Never delete data, reset production, apply migrations or alter production credentials without explicit owner approval and required preflight.
- Preserve backend listener 127.0.0.1:8001, PostgreSQL 5432, database sb_app, API prefix /api, existing EC2/Nginx/Gunicorn, Amplify hosting and systemd service/timer unless a verified change is explicitly approved.
- Use Swagger/OpenAPI first for API route, schema, authentication and request/response issues.
- Use AWS only when evidence indicates runtime, hosting, networking, environment, deployment or infrastructure issues.
- Do not create a new repository, database, cloud server or paid integration as part of ordinary tool selection.
- Private repository access is least-privilege. Read-only is the default for research/review tools; write access requires a defined task.
- No AI tool may merge, bypass branch protection, deploy, change production data/secrets/infrastructure or approve its own protected work.

## 8. Mobile-first capability rule

The assigned job must be possible through an Android/iOS app or mobile browser, or execute in an already-approved cloud CI/automation service controllable and reviewable from mobile.

- Full task access: the assigned job can be performed from mobile.
- Companion access: mobile supports monitoring, comments, review or approvals, but not full authoring/execution. Do not assign full task execution to this tool on mobile.
- Cloud execution: a job runs in GitHub Actions or an existing approved cloud service and can be started/monitored from mobile.
- Excluded: desktop IDE, local terminal or local-model workflows required to complete the assigned job.

Verify mobile capability for the exact task, not merely the existence of an app or responsive website. This policy does not prohibit desktop work later; it excludes desktop-dependent workflows from the active phase until the owner changes the requirement.

## 9. Quota and plan maintenance

Free-plan limits, model availability and mobile capabilities change. Do not treat a quota as permanent.

- Check official pricing/usage documentation before relying on a numerical allowance.
- Verify actual account entitlements, regional availability and repository permissions before assigning a task.
- Maintain a quota note for tools with changing credits: Codex, Copilot, Jules, Gemini, Claude, Perplexity, Firecrawl, Context7, MagicPath, Deepnote, PostHog, Activepieces and OpenRouter.
- Review this register monthly or when a provider announces a plan change.
- Reclassify tools only after documenting the reason and new fallback.
- Never enable paid usage or enter payment details without owner approval.

## 10. Governance

ChatGPT, as technical CTO/coordinator, proposes policy updates when tool roles, account limits or project workflows change. The owner approves paid subscriptions, new infrastructure, permission expansion and production-impacting changes.

Every contributor must read this policy before using an AI tool or service on project work. If a tool is not listed, do not silently add it to the active stack. Propose its purpose, free limits, mobile capability, data handling, overlap and fallback first.

**Core principle:** Use the strongest free primary first, switch to an approved free fallback when its limit is reached, preserve task continuity, and never trade security or correctness for a free quota.
