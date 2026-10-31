# Super Bajaar — AI Team Collaboration & Delivery Policy

> **Canonical role and workflow details:** [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md). Read that document before assigning or accepting any AI task. This file is the short collaboration entry point; it does not duplicate the full operating model.

## Core rules

### Repository access: read is not write

Super Bajaar is a public GitHub repository, so agents may inspect public files and issue pages when their own session supports browsing. This does not imply authenticated write access or automatic task dispatch.

- **ChatGPT:** connected GitHub integration provides available read/write operations; verify each successful action and use feature branches/PRs.
- **Copilot:** optional coding assistant inside Codespaces only when explicitly invoked and Codespaces usage is available; not an issue owner or cloud coding agent.
- **Gemini:** public read access for independent read-only audits; no write access is assumed.
- **Perplexity:** public read access for context plus external research; no repository writes.
- **Claude:** public read access and patch/file delivery; direct GitHub writes are not assumed. ChatGPT handles integration.
- No agent receives production database, secrets, infrastructure or deployment access from public repository visibility.

1. GitHub issues, branches, pull requests, reviews and Actions are the shared project record. Separate AI chats do not communicate directly.
2. The project owner retains final authority over priorities, access, paid usage, protected production/database changes and releases.
3. ChatGPT is the CTO: architecture, strategy, task decomposition, allocation, integration, evidence review, PR readiness and merge execution under the repository approval policy.
4. ChatGPT leads bounded React/Vite and non-schema FastAPI/API/service implementation, bug fixes, integration and tests.
5. Gemini is the independent auditor and quality challenger. Audits/reviews are read-only; a separate non-schema implementation is allowed only with a new issue and reserved paths.
6. Perplexity performs external research and source verification; it does not implement repository code.
7. Claude owns complex backend/data-integrity work and designated SQL/schema/migration/runner work under `CLAUDE.md`.
8. Every task has exactly one accountable owner, one defined scope and explicit allowed paths. No two agents edit the same file set concurrently.
9. Copilot issues #176 and #207 are not active implementation assignments under the current plan; do not trigger cloud-agent work. Owner approval is required before reallocating or closing them.
10. Gemini CLI is an alternative interface to Gemini, not a second independent agent. Antigravity is experimental until authentication and repository permissions are verified.
11. GitHub Actions and the supporting tools are not AI task owners. Their purpose and boundaries are listed in the canonical operating model.
12. No direct push to `main`, self-merge, branch-protection bypass, production data mutation, production migration, unapproved paid usage or deployment.

## Role allocation at a glance

| Contributor | Exclusive responsibility |
|---|---|
| ChatGPT | CTO, architecture, task decomposition/allocation, coordination, integration, PR review, CI evidence review, merge readiness and authorised merge execution |
| GitHub Copilot | Optional inline coding assistance inside Codespaces when explicitly invoked and usage is available; no issue ownership or cloud-agent dispatch |
| Gemini (main) | Independent read-only module audits, defect discovery, quality/security review and separately assigned non-schema fixes only on reserved paths |
| Perplexity | External research, official documentation, vendor/API capability and source verification, Indian compliance research |
| Claude | Complex backend/data-integrity engineering and designated SQL/schema/migration/runner authoring under `CLAUDE.md` |
| Gemini CLI | Optional Gemini terminal interface; not a separate AI owner |
| Antigravity | Experimental alternative; no active production assignment until verified |
| GitHub Actions | Deterministic CI/testing/security checks; not an AI agent |
| GitHub | Canonical issue/PR/branch/permission system; not an AI worker |
| Codespaces | Preferred interactive development terminal; current usage budget exhausted, no top-up without approval |
| Context7 / Firecrawl / TinyFish | Documentation retrieval, web extraction and browser research support |
| Manufact | Authorised MCP server/deployment management, not default app deployer |
| Linear / GitLab / 3Min API | Optional supporting systems only when a task explicitly requires them |
| AWS EC2 / SSM / Amplify / Swagger | Runtime, approved infrastructure, frontend hosting and API-contract diagnostics respectively |

Supporting tools and their detailed boundaries are documented in the canonical [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md).
## Standard handoff

Every task must record: GitHub issue, accountable owner, task type/access mode, base branch and SHA, allowed/protected paths, dependencies, acceptance criteria, exact tests, evidence, risks and next owner. Completion reports must distinguish PASS, FAIL and NOT VERIFIED. Never claim an unrun test or unverified permission.

## Workflow

Intake → inspect current issues/PRs → reserve paths → assign one owner → execute within scope → self-review → independent read-only review → exact-commit CI → ChatGPT integration/evidence review → owner merge decision → separately approved deployment → post-deployment verification.

For active assignments, if a preferred contributor does not acknowledge within 60 seconds after actual delivery, ChatGPT coordinates the fallback on the same issue and scope; do not wait indefinitely or start duplicate parallel work. Copilot is not the fallback executor. A GitHub timer can notify/label the fallback but cannot execute an external AI by itself. If scopes overlap, access is missing, protected assets are implicated or paid usage is required, stop and record the blocker in GitHub. Do not improvise or duplicate work.

**Read next:** [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md), [Repository instructions](../AGENTS.md), [Development workflow](DEVELOPMENT_WORKFLOW.md), [Database change rules](DATABASE_CHANGE_RULES.md), and [optional Copilot-in-Codespaces policy](GITHUB_COPILOT.md).
