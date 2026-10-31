# Super Bajaar — AI Team Collaboration & Delivery Policy

> **Canonical role and workflow details:** [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md). Read that document before assigning or accepting any AI task. This file is the short collaboration entry point; it does not duplicate the full operating model.

## Core rules

1. GitHub issues, branches, pull requests, reviews and Actions are the shared project record. Separate AI chats do not communicate directly.
2. The project owner retains final authority over priorities, access, paid usage, merges, production data, infrastructure and releases.
3. ChatGPT is the CTO/coordinator: architecture, decomposition, ownership, handoffs, integration review and evidence review.
4. Every task has exactly one accountable owner, one defined scope and explicit allowed paths. No two agents may edit the same file set concurrently.
5. Read-only auditors and reviewers do not edit implementation branches.
6. Existing assignments are preserved. Copilot issue #176 (FastAPI route-registration audit) remains with Copilot; do not duplicate its scope.
7. Claude remains the designated default SQL/schema/migration/runner author under `CLAUDE.md`.
8. Gemini main is the independent read-only repository auditor. Gemini CLI is an alternative interface to Gemini, not a second independent AI; it currently has no active assignment because authentication/model execution was not verified and Codespaces budget is exhausted.
9. Antigravity CLI is experimental until authentication and repository permissions are verified. Perplexity is reserved for external research and source verification.
10. No direct push to `main`, self-merge, branch-protection bypass, production data mutation, production migration, paid usage or deployment without the required owner approval.

## Role allocation at a glance

| Contributor | Exclusive responsibility |
|---|---|
| ChatGPT | CTO, architecture, allocation, integration, final evidence review |
| Gemini (main) | Read-only repository/module audit and technical findings |
| Gemini CLI | Dormant alternative Gemini terminal interface; no duplicate assignment |
| Antigravity CLI | Experimental alternative; no production assignment until verified |
| Claude | SQL/schema/migration/runner and complex backend implementation on reserved paths |
| GitHub Copilot | Existing assigned issues and bounded non-schema coding tasks |
| Perplexity | External research, official documentation and source verification |
| GitHub Actions | Automated CI/testing; not an AI agent |

Supporting tools and their boundaries (GitHub, Codespaces, Context7, Firecrawl, TinyFish, Manufact, Linear, GitLab and 3Min API) are documented in the canonical operating model.

## Standard handoff

Every task must record: GitHub issue, accountable owner, task type/access mode, base branch and SHA, allowed/protected paths, dependencies, acceptance criteria, exact tests, evidence, risks and next owner. Completion reports must distinguish PASS, FAIL and NOT VERIFIED. Never claim an unrun test or unverified permission.

## Workflow

Intake → inspect current issues/PRs → reserve paths → assign one owner → execute within scope → self-review → independent read-only review → exact-commit CI → ChatGPT integration/evidence review → owner merge decision → separately approved deployment → post-deployment verification.

If scopes overlap, access is missing, protected assets are implicated or paid usage is required, stop and record the blocker in GitHub. Do not improvise or duplicate work.

**Read next:** [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md), [Repository instructions](../AGENTS.md), [Development workflow](DEVELOPMENT_WORKFLOW.md), [Database change rules](DATABASE_CHANGE_RULES.md), and [Copilot policy](GITHUB_COPILOT.md).
