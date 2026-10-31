# Super Bajaar — AI Team Collaboration & Delivery Policy

> Canonical details: [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md).

## Final team rules — 31 October 2026
1. **ChatGPT leads as CTO:** architecture, planning, task allocation, GitHub coordination, integration, documentation, technical review, evidence and release readiness.
2. **Gemini and Perplexity are equal engineering partners:** balanced frontend/backend implementation, debugging, tests, audits and independent reviews. Rotate implementation ownership and reserve separate paths.
3. **Perplexity may edit assigned code using owner-granted access, but must not commit or push.** Return full diff/patch, changed paths and test evidence to ChatGPT for integration.
4. **Claude owns database specialism:** SQL, schema, migrations, runner, database CI and complex data-integrity/backend work under `CLAUDE.md` and database rules.
5. **Copilot is standby only:** Codespaces quota is exhausted. No active dependency or paid top-up without approval.
6. **Google Cloud is excluded:** no access is available; no GCP task, deployment or resource creation is assumed.
7. GitHub issues, branches, PRs and Actions are the shared record. Separate AI chats do not communicate automatically; use written handoffs.
8. One task has one owner, one reviewer and exact reserved paths. No concurrent edits to the same files.
9. No direct push to `main`, self-merge, branch-protection bypass, unapproved spend, production data mutation, production migration or deployment.
10. Current production remains AWS EC2 + Nginx/Gunicorn + Amplify unless owner approves a verified migration.

## Role allocation

| Contributor | Responsibility |
|---|---|
| ChatGPT | CTO, architecture, planning, assignment, coordination, integration, review and release readiness |
| Gemini | Equal engineering partner: implementation, debugging, testing, module audits and independent review |
| Perplexity | Equal engineering partner: implementation, debugging, research, testing and independent review; no commit/push |
| Claude | Complex backend/data integrity and designated SQL/schema/migration/runner author |
| Copilot | Standby; Codespaces-dependent |
| Google Cloud | Unavailable; excluded from active operations |
| GitHub Actions | CI/build/test/security/policy automation |
| GitHub | Canonical issues/branches/PRs/reviews |

## Delivery workflow
Intake → inspect GitHub queue → define scope/acceptance → classify schema/non-schema → assign one owner and reserve paths → implement on feature branch → independent review → ChatGPT integration/evidence audit → exact-commit CI → owner merge approval → separately approved deployment → post-deployment verification.

Every task includes owner, reviewer, task type, base SHA, allowed/protected paths, dependencies, acceptance criteria, tests, evidence, risks, next owner and approval gates. Report PASS / FAIL / NOT VERIFIED accurately.

Read [Agent Task Commands](AI_AGENT_TASK_CHECK_COMMANDS.md), [Repository instructions](../AGENTS.md), [Database Change Rules](DATABASE_CHANGE_RULES.md) and [Development Workflow](DEVELOPMENT_WORKFLOW.md).
