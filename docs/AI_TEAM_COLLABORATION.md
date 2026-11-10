# Super Bajaar — AI Team Collaboration & Delivery Policy

> Canonical details: [AI Engineering Operating Model](AI_ENGINEERING_OPERATING_MODEL.md). The active review group is the repository owner, ChatGPT and Perplexity.

## Active team rules — 1 November 2026
1. **ChatGPT is CTO and lead technical reviewer:** architecture, planning, task allocation, GitHub coordination, integration, technical audit, evidence review and release readiness.
2. **Perplexity is the independent technical reviewer:** source verification, API/UI review, testing and independent audits; it may implement explicitly assigned work but must not commit or push.
3. **Repository owner is the only final approver:** all merge and production-release decisions remain with the owner. AI review findings are advisory and never count as formal GitHub approval.
4. **Copilot is a secondary coding agent only:** optional bounded coding, code suggestions, debugging assistance and test suggestions when usage/access is available. It is excluded from PR review, approval, reviewer assignment, review automation and release gates.
5. **Claude retains database specialism:** SQL, schema, migrations, runner, database CI and complex data-integrity/backend work under `CLAUDE.md` and database rules. Claude is not part of the active PR approval group.
6. Gemini is not part of the active review/approval chain under this policy unless the owner explicitly changes the policy.
7. GitHub issues, branches, PRs and Actions are the shared record. Separate AI chats do not communicate automatically; use written handoffs.
8. One task has one owner, one reviewer and exact reserved paths. No concurrent edits to the same files.
9. No direct push to `main`, self-merge, branch-protection bypass, unapproved spend, production data mutation, production migration or deployment.
10. Current production remains AWS EC2 + Nginx/Gunicorn + Amplify unless owner approves a verified migration.

## Role allocation

| Contributor | Responsibility |
|---|---|
| Repository owner | Sole formal GitHub approver, merge authority and production-release decision-maker |
| ChatGPT | CTO, lead technical reviewer, architecture, planning, coordination, integration and release-readiness audit |
| Perplexity | Independent technical reviewer; assigned implementation/testing/research; no commit/push |
| Copilot | Secondary coding agent only; no PR reviews, approvals, reviewer assignments or release gates |
| Claude | Designated database/SQL/schema/migration/runner specialist; not a formal approver |
| Gemini | Not in the active review/approval chain unless owner changes this policy |
| GitHub Actions | CI/build/test/security/policy automation; no AI review authority |
| GitHub | Canonical issues/branches/PRs/reviews |

## Delivery workflow
Intake → inspect GitHub queue → define scope/acceptance → classify schema/non-schema → assign one owner and reserve paths → implement on feature branch → independent review → ChatGPT integration/evidence audit → exact-commit CI → owner merge approval → separately approved deployment → post-deployment verification.

Every task includes owner, reviewer, task type, base SHA, allowed/protected paths, dependencies, acceptance criteria, tests, evidence, risks, next owner and approval gates. Report PASS / FAIL / NOT VERIFIED accurately.

Read [Agent Task Commands](AI_AGENT_TASK_CHECK_COMMANDS.md), [Repository instructions](../AGENTS.md), [Database Change Rules](DATABASE_CHANGE_RULES.md) and [Development Workflow](DEVELOPMENT_WORKFLOW.md).
