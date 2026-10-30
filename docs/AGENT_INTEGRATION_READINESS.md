# AI Agent Integration Readiness Register

> **Status:** Live readiness register; provider connections are verified individually, never inferred from product names or workspace descriptions.
> **Last checked:** 31 October 2026
> **Canonical queue:** GitHub Issues in `siinghniibandhan-wq/superbajaar`
> **Architecture:** [AI Agent Orchestration Architecture](AGENT_ORCHESTRATION_ARCHITECTURE.md)

## 1. Purpose

Track which AI agents can actually participate in the Superbajaar delivery workflow, what they can safely do, and what evidence is still missing. A tool is not integrated merely because it is installed, appears in a list, has a project, or can read public pages.

## 2. Verified platform foundation

| Component | Observed state | Evidence / limitation |
|---|---|---|
| GitHub repository | Connected to the current ChatGPT GitHub integration with admin-level repository permissions | Repository metadata for `siinghniibandhan-wq/superbajaar` returned admin/maintain/push permissions |
| Orchestration PR | PR #177 is open, mergeable and not merged | Feature branch `docs/tool-utilisation-policy-2026-10`; owner review/merge required |
| Manual pilot tracking | Issue #178 tracks the existing Lovable read-only compatibility audit; issue #179 prepares the first Jules test-only pilot | Lovable audit is running; Jules task is READY TO CONNECT but must not be dispatched until the GitHub App is installed and repository access is verified |
| GitHub CI | Latest verified PR head passed backend tests, both frontend builds and issue-form/governance workflow validation | Run 41120122844 |
| PostgreSQL migration CI | PostgreSQL 15 and 16 schema-file checks passed against disposable CI databases | Run 41120122917; no production DB was touched |
| Task-governance workflow | Present on PR branch; not active on default branch until owner merges | `.github/workflows/agent-task-governance.yml` |
| Issue form | Present on PR branch; not active on default branch until owner merges | `.github/ISSUE_TEMPLATE/agent-work-task.yml` |

## 3. Provider readiness

Statuses mean:
- **READY FOR PILOT:** exact integration and access have been tested for a bounded task.
- **AUDIT RUNNING:** an actual read-only task is currently executing; not yet accepted as an integrated agent.
- **MANUAL ONLY:** use through the provider's own app and copy structured handoffs into GitHub.
- **UNVERIFIED:** account plan, repository access, API/agent feature or mobile execution is not confirmed.
- **NOT AVAILABLE IN CURRENT TOOL SESSION:** no callable provider execution adapter is exposed here; this does not imply the user lacks an account.

| Provider / tool | Intended role | Current status | Safe next step |
|---|---|---|---|
| ChatGPT | Technical coordinator, architecture, task decomposition, integration and evidence review | Active in this session; GitHub repository access verified | Coordinate from GitHub; never claim another agent is running without a confirmed task/run |
| GitHub Actions | CI and deterministic task governance | CI verified; task-governance workflow staged in PR #177 | After merge, test issue open/edit/reopen and label transitions on a non-production test issue |
| Lovable — SuperBajaar Connect | UI/design audit and possibly isolated frontend prototyping | **AUDIT RUNNING**; existing project is ready, but no custom workspace connectors are connected; exact GitHub repository binding is not verified | Wait for the existing read-only compatibility audit. Keep the project read-only and isolated until the audit proves its source binding and technical compatibility |
| OpenAI Codex | Primary scoped coding agent under the tool policy | UNVERIFIED in this current tool session; no direct Codex task-dispatch adapter is exposed | Verify account entitlement, mobile/cloud task execution, private-repository access and branch-scoped output before first dispatch |
| GitHub Copilot | In-editor assistance; possible cloud agent if already on a paid Copilot plan | **FREE CLOUD-AGENT ACCESS NOT AVAILABLE.** Official GitHub docs state Copilot cloud agent is available on paid Copilot plans; Copilot Free does not qualify. No direct Copilot dispatch adapter is exposed in this session | Keep Copilot Free as an in-editor helper. Only use cloud-agent assignment if the account already has an eligible paid plan and repository access is enabled. [Copilot cloud agent eligibility](https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/overview), [Copilot Free](https://docs.github.com/en/copilot/how-tos/manage-your-account/get-started-with-a-copilot-plan) |
| Google Jules | First candidate for a free asynchronous GitHub coding-agent pilot | **FREE PLAN VERIFIED; account/repository installation still unverified.** Official Jules plan lists 15 tasks per rolling 24 hours and 3 concurrent tasks; its GitHub integration supports selecting a repository/branch, reviewing a plan before changes and using the `jules` issue label to start a task | Connect Jules to GitHub and select only this repository. Start with a bounded, non-sensitive task on a feature branch. Do not use the alpha REST API or create an API key for the first pilot. [Getting started](https://jules.google/docs), [limits](https://jules.google/docs/usage-limits/), [GitHub issue-label workflow](https://jules.google/) |
| Claude | Complex implementation/review and designated database-author role under repository rules | MANUAL ONLY from this session; no direct Claude execution adapter exposed | Use provider app with exact issue packet; report findings/PR/commit back to GitHub. Preserve database-author and owner approval rules |
| Perplexity | Source-backed research and read-only repository audit | UNVERIFIED for private repository coverage; no direct dispatch adapter exposed | Verify exact private-repository and branch access before assigning any repository audit; otherwise provide public sources or selected sanitized excerpts |
| Gemini | Independent architecture, UI and code review | MANUAL ONLY from this session; no direct Gemini execution adapter exposed | Provide selected diffs, screenshots or sanitized excerpts and record the review in the GitHub issue |
| Other coding agents | Specialist fallback | UNVERIFIED | Add only when a specific task need, supported access, quota and safe handoff are demonstrated |

**Lovable audit currently in progress:** The existing SuperBajaar Connect project has a user-submitted read-only compatibility audit request. The latest message status was `running` at last check. Project metadata reports latest commit `abcccc904fdf8962f363089e8d7d6e2c3a7e1a4f`; the branch and remote repository binding are not exposed by the inspected project metadata. The workspace connector list returned zero connectors and project knowledge was empty. Read-only file inspection found `.lovable/project.json` declares template `tanstack_start_ts_current`; `package.json` declares TanStack Start 1.168.60, React 19.2, Vite 8.1.5 and Tailwind CSS 4, with no Supabase/Firebase SDK dependency in the manifest; the route tree currently exposes only the root route and `src/routes/index.tsx` is a blank-page placeholder; `src/server.ts` is a TanStack SSR server entry; `src/styles.css` contains a default neutral OKLCH theme; `src/hooks/use-mobile.tsx` exists but there is no populated product UI from which to validate responsive behaviour. Its `AGENTS.md` contains Lovable-generated sync guidance but does not identify the canonical Superbajaar repository. A prior assistant response in this project stated that GitHub sync creates a new repository and cannot attach this project to an existing repository; this is not a substitute for a verifiable remote binding. These findings indicate a separate TanStack application, not the production React + Vite application. Current official Lovable GitHub integration documentation explicitly states that connecting a Lovable project creates a new repository and that linking to a repository that already exists is not supported; importing an existing codebase creates a new project copy, which can then sync to a newly created repository. See [Lovable's official GitHub integration guide](https://docs.lovable.dev/integrations/github) and [official FAQ](https://docs.lovable.dev/introduction/faq). This confirms that the existing Lovable project cannot become a safe two-way writer for the canonical Superbajaar repository through normal Git sync. It could only be used as a visual prototype/design reference or an isolated UI experiment, with manually exported artifacts and human integration later. Keep it isolated/read-only unless the owner specifically approves a separate isolated prototype workflow. Do not send additional implementation prompts to that project until the audit completes and is reviewed.

## 4. Integration order

1. **Merge and activate the GitHub foundation:** owner reviews/merges PR #177. Then create a test agent issue and verify that the issue workflow creates status labels, sets READY for a complete issue, and sets BLOCKED for an incomplete issue.
2. **Complete the manual pilot:** issue #178 tracks the running Lovable read-only compatibility audit. After PR #177 is merged, validate its status labels and handoff. Issue #179 is the first Jules test-only pilot; dispatch only after the owner connects the Jules GitHub App to this repository.
3. **Accept or isolate Lovable:** review the running compatibility audit. If it cannot prove a safe canonical source workflow, retain it only for design concepts and screenshots; do not use it to edit or deploy the production application.
4. **Select the first coding agent:** Codex remains the policy primary when its account entitlement and mobile/cloud execution are verified. For the first free asynchronous GitHub pilot, Jules is the preferred candidate because its official free plan supports 15 tasks per rolling 24 hours and three concurrent tasks, matching the initial concurrency ceiling. The user must connect the Jules GitHub App and select only this repository. Copilot cloud agent is not a free-tier fallback; GitHub documents it as a paid Copilot feature.
5. **Run one bounded coding pilot:** one issue, one owner, one feature branch, explicit file allowlist, no schema or production impact, independent review, CI and owner merge.
6. **Add the next provider only after the first adapter is stable:** reuse the same task packet, status model and handoff report. Never build separate queues per provider.

## 5. Provider integration acceptance checklist

A provider is marked READY FOR PILOT only after all applicable checks pass:

- [ ] Account entitlement and regional availability verified.
- [ ] Free quota/usage limit verified from the actual account or official current documentation.
- [ ] Repository access to the correct private/public repository verified.
- [ ] Branch and file-scope controls understood and tested.
- [ ] Mobile dispatch and result review verified, or the tool is explicitly classified as companion/manual only.
- [ ] Task submission/acceptance is observable.
- [ ] Stable task/run identifier is recorded where supported.
- [ ] Completion/failure/timeout can be observed.
- [ ] Structured findings, commit or PR can be returned to GitHub.
- [ ] Duplicate dispatch and retry behaviour understood.
- [ ] Secrets and sensitive-data handling reviewed.
- [ ] Paid usage, new permissions or external data transfer approved if required.
- [ ] One bounded pilot completed with evidence and no overlapping writes.

If the provider cannot satisfy API-based dispatch, it may still be used manually. Do not claim automated integration in that case.

## 6. Non-negotiable restrictions

- GitHub remains the source of truth; no private chat is treated as durable project state.
- Read-only is the default for research/review agents.
- No two writers may edit the same file concurrently.
- No agent merges to `main`, bypasses checks, changes production data/secrets/infrastructure, applies migrations or deploys.
- Preserve the established FastAPI/PostgreSQL/Amplify/EC2 architecture and existing ports unless the owner approves a verified change.
- No new server, database, paid subscription, API billing or permission expansion without explicit owner approval.
- An assignment is not a running task. Record provider acceptance or a real run ID before changing state to IN PROGRESS.

## 7. Execution evidence for pilot issue #178

- GitHub issue #178: `[AGENT TASK] Pilot 1 — Lovable compatibility audit`; open; task body uses the `###` headings expected by the validator.
- Existing Lovable project audit message remains RUNNING; no final audit report has been returned yet. No implementation prompts or writes were sent to that project.
- Preliminary coordinator-side inspection of Lovable project ref `abcccc904fdf8962f363089e8d7d6e2c3a7e1a4f` confirms the TanStack Start template, a placeholder root page, a standalone server entry, and empty workspace connector/project-knowledge state. Full recommendation remains KEEP ISOLATED pending completion of the audit.
- The latest local state-machine test script exercises complete -> READY, incomplete -> BLOCKED and reopened DONE -> READY. It uses a mocked GitHub issue/API surface; it does not call GitHub or dispatch an agent.
- Latest PR workflow execution for head `cb319e3641f512276557e6ea877095e3bf9fddd0` was queued at last check. Do not mark the latest test run successful until GitHub reports the terminal conclusion.

## 8. Current blockers and next checkpoint

1. **Owner action:** review and merge PR #177. The PR is mergeable; it remains unmerged by design because the repository policy reserves merge authority to the owner.
2. **GitHub test:** after merge, create a test issue and verify the issue-event workflow on the default branch.
3. **Lovable:** wait for the current read-only audit to finish; do not send a second prompt or modify that project while the audit is running.
4. **External coding agent:** no provider adapter is yet verified in this session. The first provider is selected only after its account and repository access are proven.

**Definition of integrated:** A provider is integrated only when a real task can be safely dispatched or manually handed off, its execution is observable, its result is recorded in GitHub, and the owner can review the output. An app listing, OAuth connection or documentation entry alone is not integration.
