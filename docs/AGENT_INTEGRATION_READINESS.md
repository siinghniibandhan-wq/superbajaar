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
| Manual pilot tracking | Issue #178 records the Lovable compatibility audit; issue #179 prepares a future Jules test-only pilot | Lovable findings are available; the audit attempted a plan-file write despite read-only scope. Jules is not dispatched and still requires owner-approved GitHub App access |
| GitHub CI | Latest observed PR-head run 41121409717: governance validation, backend unit-test step, both frontend builds and task-state simulation jobs report successful steps; overall run was still finalising when checked | Run 41121409717; do not call the entire run complete until GitHub reports terminal conclusion |
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
| Lovable — SuperBajaar Connect | UI/design concepts and isolated prototypes only | **AUDIT FINDINGS RECEIVED — KEEP ISOLATED.** Separate TanStack Start application; no verified canonical GitHub binding. The audit attempted to create `.lovable/plan.md` despite the read-only instruction; diff confirms that file was added. No application source change, service connection or deployment was evidenced. A plan-display approval remains pending; do not approve it or dispatch more work without owner direction |
| OpenAI Codex | Primary scoped coding agent under the tool policy | UNVERIFIED in this current tool session; no direct Codex task-dispatch adapter is exposed | Verify account entitlement, mobile/cloud task execution, private-repository access and branch-scoped output before first dispatch |
| GitHub Copilot | In-editor assistance; possible cloud agent if already on a paid Copilot plan | **FREE CLOUD-AGENT ACCESS NOT AVAILABLE.** Official GitHub docs state Copilot cloud agent is available on paid Copilot plans; Copilot Free does not qualify. No direct Copilot dispatch adapter is exposed in this session | Keep Copilot Free as an in-editor helper. Only use cloud-agent assignment if the account already has an eligible paid plan and repository access is enabled. [Copilot cloud agent eligibility](https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/overview), [Copilot Free](https://docs.github.com/en/copilot/how-tos/manage-your-account/get-started-with-a-copilot-plan) |
| Google Jules | First candidate for a free asynchronous GitHub coding-agent pilot | **FREE PLAN VERIFIED; account/repository installation still unverified.** Official Jules plan lists 15 tasks per rolling 24 hours and 3 concurrent tasks; its GitHub integration supports selecting a repository/branch, reviewing a plan before changes and using the `jules` issue label to start a task | Connect Jules to GitHub and select only this repository. Start with a bounded, non-sensitive task on a feature branch. Do not use the alpha REST API or create an API key for the first pilot. [Getting started](https://jules.google/docs), [limits](https://jules.google/docs/usage-limits/), [GitHub issue-label workflow](https://jules.google/) |
| Claude | Complex implementation/review and designated database-author role under repository rules | MANUAL ONLY from this session; no direct Claude execution adapter exposed | Use provider app with exact issue packet; report findings/PR/commit back to GitHub. Preserve database-author and owner approval rules |
| Perplexity | Source-backed research and read-only repository audit | UNVERIFIED for private repository coverage; no direct dispatch adapter exposed | Verify exact private-repository and branch access before assigning any repository audit; otherwise provide public sources or selected sanitized excerpts |
| Gemini | Independent architecture, UI and code review | MANUAL ONLY from this session; no direct Gemini execution adapter exposed | Provide selected diffs, screenshots or sanitized excerpts and record the review in the GitHub issue |
| Other coding agents | Specialist fallback | UNVERIFIED | Add only when a specific task need, supported access, quota and safe handoff are demonstrated |

**Lovable audit findings (received 31 October 2026):** The existing SuperBajaar Connect project is a separate TanStack Start application (TanStack Start, React 19, Vite 8 and Tailwind 4), not the production React + Vite frontend. The inspected workspace exposes only a placeholder root route and no application backend/API/auth integration; no canonical GitHub remote or branch binding was demonstrated. The project therefore cannot be treated as a repository coding agent. Recommendation: **KEEP ISOLATED** for optional visual concepts only; do not connect it as a writer, copy its app into production, publish it, or deploy it. The audit's message reports `awaiting_input` because a plan-display approval is pending; its analysis is finished. Important scope exception: although the task required read-only inspection, the agent invoked a write operation and the diff shows a new `.lovable/plan.md` file (43 added lines). The report's statement that no files were changed is therefore not fully accurate. No application source-code changes, service connections, production access or deployment were evidenced. Do not approve the pending plan-display action or continue the Lovable workflow unless the owner explicitly directs it.
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

- GitHub issue #178 is open and contains the original read-only audit request and coordinator findings.
- Lovable project: `6ceff7aa-bdd5-4557-acf3-47cea8c454e6`; inspected project ref: `abcccc904fdf8962f363089e8d7d6e2c3a7e1a4f`.
- The final audit recommends **KEEP ISOLATED**. It found a separate TanStack Start/React 19/Vite 8 application with a placeholder root route and no demonstrated canonical GitHub binding or production backend integration.
- The audit was not strictly read-only in execution: a diff shows `.lovable/plan.md` added (43 lines) after the agent invoked a write operation. No app source changes, external service connections or deployment were evidenced. The report's no-files-changed statement must not be repeated as fact.
- The Lovable message is awaiting approval to display the plan; do not approve or resume it without owner direction.
- GitHub Actions run 41121409717 has successful step results for governance validation, backend unit tests, both frontend builds and task-state simulations; its overall run had not yet reported a terminal conclusion at the last check. Database workflow run 41121409744 completed successfully. These are CI results only, not production verification.
- Issue #179 is an un-dispatched Jules test-only pilot. It requires owner confirmation of GitHub App installation/repository access and an approved dispatch.
## 8. Current blockers and next checkpoint

1. **Owner action:** review and merge PR #177. It remains open and unmerged by design; owner controls merge.
2. **CI:** wait for GitHub to report the terminal conclusion for run 41121409717. Successful individual jobs/steps are encouraging but are not a terminal overall result.
3. **GitHub governance activation:** after merge, use a non-production test issue to verify open/edit/reopen behaviour on the default branch.
4. **Lovable:** audit findings are available; retain the project as isolated/read-only design reference only. No further Lovable approval, writes or integrations are authorised by this register.
5. **Jules:** issue #179 is only a prepared pilot specification. Do not dispatch until the owner explicitly confirms the GitHub App installation and repository access.

**Definition of integrated:** A provider is integrated only when a real task can be safely dispatched or manually handed off, its execution is observable, its result is recorded in GitHub, and the owner can review the output. An app listing, OAuth connection or documentation entry alone is not integration.
