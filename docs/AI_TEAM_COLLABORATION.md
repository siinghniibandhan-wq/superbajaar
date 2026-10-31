# Super Bajaar — AI Team Collaboration & Delivery Policy

> **Canonical source:** [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md). This document is the quick-start summary; the operating model controls if wording differs.

## Current team rules — 31 October 2026

1. **ChatGPT leads the team as CTO.** It owns architecture, planning, task allocation, GitHub coordination, integration, documentation, technical review and final audit.
2. **Gemini** provides independent technical analysis, module audits, debugging hypotheses and read-only quality challenge. Implementation requires a separately assigned task and verified access.
3. **Claude** handles complex backend/data-integrity engineering and is the default SQL/schema/migration/runner specialist under `CLAUDE.md` and database rules.
4. **Perplexity** handles research, source verification and independent audits. The owner has granted it code-edit access for specifically assigned tasks; it may edit but **must not commit or push**. ChatGPT reviews and integrates its changes.
5. **Google Cloud** remains in the infrastructure planning loop for cloud architecture, IAM, compute, storage, networking, monitoring and cost analysis. It is a platform/workstream, not an AI agent. No direct GCP console integration is assumed.
6. **GitHub Copilot is standby only**, dependent on Codespaces availability and usage. Codespaces quota is currently exhausted; Copilot is not an active coding dependency and no paid top-up is authorised.
7. GitHub issues, branches, PRs and Actions are the single project record. Separate AI chats do not communicate automatically; use written handoffs in GitHub.
8. One task has one accountable owner, one reviewer and exact allowed paths. No concurrent edits to the same file set.
9. No direct push to `main`, self-merge, branch-protection bypass, unapproved paid usage, production data mutation, production migration or deployment.
10. Existing production remains AWS EC2 + Nginx/Gunicorn + Amplify unless the owner approves a verified migration. Google Cloud is not an automatic replacement.

## Role allocation

| Contributor | Exclusive responsibility |
|---|---|
| ChatGPT | CTO, architecture, planning, assignment, coordination, integration, review, documentation and release readiness |
| Gemini | Independent technical analysis, module audit, debugging and read-only review; separate implementation only when assigned |
| Claude | Complex backend/data integrity; designated SQL/schema/migration/runner author |
| Perplexity | External research, source verification, independent audit and assigned code edits; no commit/push |
| Google Cloud | Cloud infrastructure planning and approved GCP work; not an AI agent |
| GitHub Copilot | Standby; Codespaces-dependent only |
| GitHub Actions | CI/build/test/security/policy automation |
| GitHub | Canonical issue/branch/PR/review system |

## Delivery workflow

Intake → inspect current GitHub work → define scope and acceptance criteria → classify schema/non-schema/infrastructure → assign one owner and reserve paths → implement on feature branch → independent read-only review → ChatGPT integration and evidence audit → exact-commit CI → owner merge approval → separately approved deployment → post-deployment verification.

## Handoff requirements

Every issue must include owner, reviewer, task type, base branch/SHA, allowed and protected paths, dependencies, acceptance criteria, tests, evidence, risks, schema/infrastructure/paid impact and next owner. Report PASS / FAIL / NOT VERIFIED accurately. A task is not complete merely because an agent says it is done.

## Important access boundary

The user's separate Gemini, Claude and Perplexity subscriptions are not automatically connected to this ChatGPT session. Use available verified integrations only. Otherwise ChatGPT supplies a copy/paste task brief and collects the result through GitHub or the user. Do not claim cross-agent dispatch or execution without evidence.

Read the full [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md), [Agent task commands](AI_AGENT_TASK_CHECK_COMMANDS.md), [Repository instructions](../AGENTS.md), [Database change rules](DATABASE_CHANGE_RULES.md), and [Development workflow](DEVELOPMENT_WORKFLOW.md).
