# Super Bajaar — AI Team Collaboration & Delivery Policy

> **Purpose:** A shared operating agreement for the human owner and the AI tools assisting this repository. GitHub issues, branches, commits, pull requests and Actions are the durable project record. Separate AI chat sessions do not share memory or communicate directly; the owner or coordinator carries handoffs through these shared artifacts.

## 1. Principles

1. **One team, distinct strengths.** Contributors are collaborators, not a command hierarchy. Every reviewer may challenge an assumption with evidence; disagreement is resolved through the owner, documented decisions and reproducible tests.
2. **The owner has final authority.** The project owner sets priorities and approves merges, production data changes, secrets, infrastructure changes and releases.
3. **ChatGPT coordinates; it does not invent execution.** It acts as technical lead/coordinator for architecture, task decomposition, integration, evidence review and documentation. It must not claim a test, edit, commit, connection or deployment happened unless the relevant tool or runner confirms it.
4. **Small, non-overlapping assignments.** Claude and Copilot tasks should normally be limited to 2–3 related files per batch. Assign different files to different agents. Never let two agents edit the same files concurrently.
5. **Evidence beats confidence.** Report exact paths, commit SHAs, commands, CI runs and observed outcomes. Suggestions are not test results.
6. **Protect working systems.** Preserve established architecture and unrelated working code. Do not widen a task without approval.

## 2. Roles and boundaries

| Contributor | Primary contribution | Appropriate assignments | Boundaries |
|---|---|---|---|
| Project owner (human) | Product direction and final decisions | Priorities, acceptance criteria, approvals, merge and release decisions | Retains final authority over repository and production |
| ChatGPT | Technical lead and coordinator | Architecture, task planning, decomposition, cross-agent handoffs, integration review, documentation, CI/evidence audit | Cannot claim work performed by another AI; cannot merge/deploy or alter production without explicit approval |
| Claude | Primary complex implementation partner; designated default SQL/schema/migration and runner author under `CLAUDE.md` | Complex code investigation and implementation, scoped backend work, approved database change drafts, migration/runner work under the database policy | Must use feature branches and small 2–3-file batches where practical; owner approval remains mandatory |
| GitHub Copilot | Repository-aware coding assistant | Code completion, bounded implementation, explanations, test scaffolding and first-pass review when enabled | Free-plan capabilities may not include cloud agent; verify account access. Not authorised to take over protected SQL/migration authorship, merge or deploy |
| Perplexity | Proposed independent research and repository audit partner | Read-only codebase discovery, technical research, source-backed fact checking, documentation consistency and independent findings | Treat repository access and private-repo/branch coverage as unverified until tested. Begin read-only; do not grant write access by default |
| Gemini | Independent reviewer and challenger | Review pasted diffs, code excerpts, screenshots, UX, architecture and technical explanations | Do not assume ZIP extraction or repository access; provide the exact material needed for review |
| GitHub Actions | Automated quality gate | Repeatable frontend, backend, database and policy checks on commits/PRs | CI does not prove production state, live data integrity, deployment or complete end-to-end workflows |

**Capability verification:** A product being discussed, installed or connected does not prove a particular plan, permission, model, repository scope or agent feature is available. Verify the actual account and integration before assigning work that depends on it. Do not state Perplexity is connected or Copilot cloud agent is available until the relevant account/repository test confirms it.

## 3. Work allocation and batch cadence

- Use two focused work windows per day when practical, separated by approximately 3–4 hours. This is a planning preference, not an automatic schedule or promise of background execution.
- Each Claude/Copilot implementation batch should normally touch no more than 2–3 related files. If the task genuinely needs more, split it into reviewable batches or explain why the scope cannot be split.
- Batch 2 starts only after Batch 1 has been reviewed, its handoff is complete and no unresolved conflict remains.
- Assign one implementation owner per file set. A second AI may review the resulting diff read-only; it must not independently edit the same files.
- Perplexity starts with read-only discovery/audit. Gemini receives selected excerpts/diffs/screenshots for independent challenge.
- Keep tasks independent where possible. If one task depends on another, record the dependency and wait for its accepted output.
- Do not consume limited free-tier context/credits on repeated broad repository scans. Give each agent a precise task, relevant paths and acceptance criteria.

## 4. Standard delivery lifecycle

1. **Discover:** inspect the current repository, issue, branch, relevant docs and actual implementation. Identify unknowns and protected files.
2. **Plan:** coordinator proposes a small task with owner, file allowlist, acceptance criteria, dependencies and verification commands.
3. **Assign:** create or update a GitHub issue with one accountable implementation owner and a separate reviewer where useful.
4. **Implement:** work on a feature branch from the latest `main`; touch only assigned files and preserve unrelated changes.
5. **Self-review:** author inspects the complete diff, adds relevant tests/docs and reports limitations.
6. **Independent review:** a different contributor reviews the diff without editing the same files; disagreements are recorded with evidence.
7. **Verify:** run appropriate local checks and GitHub Actions on the exact commit. Record skipped or unavailable checks honestly.
8. **Integrate:** coordinator checks cross-file consistency, architecture, security, schema impact, documentation and CI.
9. **Approve:** owner reviews the final PR and decides whether to merge.
10. **Release:** deployment and production verification are separate steps requiring explicit owner approval and evidence.

## 5. Required task handoff

Every AI assignment and completion report must use this compact structure:

```text
Task ID / GitHub issue:
Assigned role:
Base branch and starting commit:
Allowed files:
Files inspected:
Files changed:
Summary and rationale:
Acceptance criteria: PASS / FAIL / NOT VERIFIED
Commands/tests actually run:
Exact results and CI run/commit:
Known risks or unresolved questions:
Dependencies / next owner:
Files and systems deliberately left untouched:
Production/deployment impact: NONE / PROPOSED / APPROVED / VERIFIED
```

Do not report a test as passed if it was only suggested, inspected or expected to pass. If the environment cannot run it, state NOT RUN and provide the reason.

## 6. GitHub as the shared memory

- Use issues for task scope, owner, dependencies, questions and handoff.
- Use branches for isolated work; use descriptive names such as `feat/<scope>-<date>`, `fix/<scope>-<date>` or `docs/<scope>-<date>`.
- Use PR descriptions for changed files, behaviour, acceptance criteria, test evidence, documentation impact and schema/deployment impact.
- Use review comments for actionable findings and decisions.
- Use `IMPORTANT_UPDATES.md` for dated, material project decisions and verified milestones.
- Link related issues, PRs, commits and CI runs. Do not rely on one AI chat as the only record.
- No AI session can see another session's private conversation unless the owner explicitly relays the information or records it in GitHub.

## 7. Repository and production safeguards

All contributors must follow `AGENTS.md`, `CLAUDE.md` where applicable, and `docs/DATABASE_CHANGE_RULES.md`.

- Never push directly to `main`; create a focused branch from the latest `main`.
- Never merge your own work, bypass required checks or alter branch protection.
- Do not edit, rename, delete, regenerate or reformat historical/applied migrations.
- Do not change `backend/schema_required.txt`, migration runners, database CI policy or protected schema assets outside the approved owner-controlled process.
- Claude remains the designated default SQL/schema/migration and runner author under `CLAUDE.md`; all database work remains subject to owner/database-owner approval.
- Never reset, drop, truncate, bulk-delete or manually alter production data; never apply production SQL/migrations without explicit approval and the required preflight.
- Never expose secrets, tokens, credentials, connection strings, private customer/payment data or production `.env` values.
- Do not add paid services, enable paid AI usage, install dependencies or broaden external permissions without explaining the need and obtaining approval.
- Preserve backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, public API prefix `/api`, existing EC2/Nginx/Gunicorn, Amplify and systemd service/timer arrangement unless the owner approves a verified change.
- A merge is not a deployment. Green CI is not production verification.

## 8. Conflict resolution and stop conditions

Pause and ask the owner when instructions conflict, a task exceeds its file allowlist, protected database/production assets are implicated, repository access is incomplete, an agent's plan/permissions are unclear, or evidence contradicts an earlier assumption. Explain the exact conflict, impact and safe options. Respectful disagreement is encouraged; silent scope expansion is not.

## 9. Suggested first use of each partner

- **Claude:** complex implementation or database-author work only after a precise task and relevant documents are supplied.
- **Copilot:** bounded repository task or test assistance only for features enabled on the actual account; Free-tier cloud-agent access must not be assumed.
- **Perplexity:** read-only repository audit after its GitHub connection and accessible repository/branch scope are verified.
- **Gemini:** independent review of selected diffs, excerpts, architecture or UI screenshots.
- **ChatGPT:** create the issue/task brief, coordinate ownership, compare findings, inspect integration evidence and prepare the final review for the owner.

**Maintenance:** Review this policy when contributor roles, actual account capabilities, repository access or project governance changes. Keep account entitlements explicitly marked verified or unverified.
