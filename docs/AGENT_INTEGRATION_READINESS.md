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
| Manual pilot tracking | Issue #178 tracks the existing Lovable read-only compatibility audit | Existing Lovable task is already running; issue records its message ID and read-only scope |
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
| GitHub Copilot | GitHub-native coding assistance and possible cloud coding-agent pilot | UNVERIFIED; no direct Copilot dispatch adapter is exposed in this session | Verify actual plan and whether coding-agent assignment is enabled for this repository; use one bounded, non-sensitive pilot issue |
| Google Jules | Asynchronous GitHub coding tasks | UNVERIFIED; no direct Jules dispatch adapter is exposed in this session | Verify current availability, free quota, repository installation, branch output and status reporting |
| Claude | Complex implementation/review and designated database-author role under repository rules | MANUAL ONLY from this session; no direct Claude execution adapter exposed | Use provider app with exact issue packet; report findings/PR/commit back to GitHub. Preserve database-author and owner approval rules |
| Perplexity | Source-backed research and read-only repository audit | UNVERIFIED for private repository coverage; no direct dispatch adapter exposed | Verify exact private-repository and branch access before assigning any repository audit; otherwise provide public sources or selected sanitized excerpts |
| Gemini | Independent architecture, UI and code review | MANUAL ONLY from this session; no direct Gemini execution adapter exposed | Provide selected diffs, screenshots or sanitized excerpts and record the review in the GitHub issue |
| Other coding agents | Specialist fallback | UNVERIFIED | Add only when a specific task need, supported access, quota and safe handoff are demonstrated |

**Lovable audit currently in progress:** The existing SuperBajaar Connect project has a user-submitted read-only compatibility audit request. The latest message status was `running` at last check. Project metadata reports latest commit `abcccc904fdf8962f363089e8d7d6e2c3a7e1a4f`; the branch and remote repository binding are not exposed by the inspected project metadata. The workspace connector list returned zero connectors and project knowledge was empty. Read-only file inspection found `.lovable/project.json` declares template `tanstack_start_ts_current`; `package.json` declares TanStack Start 1.168.60, React 19.2, Vite 8.1.5 and Tailwind CSS 4, with no Supabase/Firebase SDK dependency in the manifest; the route tree currently exposes only the root route and `src/routes/index.tsx` is a blank-page placeholder; `src/server.ts` is a TanStack SSR server entry; `src/styles.css` contains a default neutral OKLCH theme; `src/hooks/use-mobile.tsx` exists but there is no populated product UI from which to validate responsive behaviour. Its `AGENTS.md` contains Lovable-generated sync guidance but does not identify the canonical Superbajaar repository. A prior assistant response in this project stated that GitHub sync creates a new repository and cannot attach this project to an existing repository; this is not a substitute for a verifiable remote binding. These findings indicate a separate TanStack application, not the production React + Vite application. Keep it isolated/read-only unless the running audit produces stronger repository-binding evidence. Do not send additional implementation prompts to that project until the audit completes and is reviewed.

## 4. Integration order

1. **Merge and activate the GitHub foundation:** owner reviews/merges PR #177. Then create a test agent issue and verify that the issue workflow creates status labels, sets READY for a complete issue, and sets BLOCKED for an incomplete issue.
2. **Complete the manual pilot:** use one issue with independent read-only work packages. Test the task packet, handoff report, dependency recording and one-writer-per-file rule. Do not require code changes in the first pilot.
3. **Accept or isolate Lovable:** review the running compatibility audit. If it cannot prove a safe canonical source workflow, retain it only for design concepts and screenshots; do not use it to edit or deploy the production application.
4. **Select the first coding agent:** prefer the first provider whose account entitlement, private-repository access, mobile/cloud execution, branch isolation, task status and free quota are actually verified. Codex is the policy primary; Copilot or Jules can be considered as a GitHub-native alternative if available.
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

## 7. Current blockers and next checkpoint

1. **Owner action:** review and merge PR #177. The PR is mergeable; it remains unmerged by design because the repository policy reserves merge authority to the owner.
2. **GitHub test:** after merge, create a test issue and verify the issue-event workflow on the default branch.
3. **Lovable:** wait for the current read-only audit to finish; do not send a second prompt or modify that project while the audit is running.
4. **External coding agent:** no provider adapter is yet verified in this session. The first provider is selected only after its account and repository access are proven.

**Definition of integrated:** A provider is integrated only when a real task can be safely dispatched or manually handed off, its execution is observable, its result is recorded in GitHub, and the owner can review the output. An app listing, OAuth connection or documentation entry alone is not integration.
