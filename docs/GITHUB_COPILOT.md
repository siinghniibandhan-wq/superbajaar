# GitHub Copilot — plans, limits and Super Bajaar usage policy

> **Team policy:** See [AI Team Collaboration & Delivery Policy](AI_TEAM_COLLABORATION.md) for the shared role, batching, handoff and review model.
>
> **Research date:** 31 October 2026  
> **Status:** Official public GitHub documentation reviewed. The Copilot subscription actually assigned to the Super Bajaar repository contributor has **not** been independently verified. Do not assume that repository integration means a paid plan or unlimited agent access.

## 1. What Copilot is used for here

GitHub Copilot is an additional AI coding assistant for the Super Bajaar repository. It may help with code completion, explanations, refactoring, test suggestions, debugging, pull-request work and (where the user's plan and repository permissions allow) agent-driven changes.

Copilot is an assistant, not an autonomous project owner. It does not replace the repository's architecture, security, review, database governance, CI, owner-approval or release controls.

## 2. Individual plan comparison

The following is GitHub's published USD pricing and allowance at the research date. Prices are before any applicable taxes, currency conversion, bank/card fees or regional pricing. Check GitHub's live plan page before purchase.

| Plan | Published price | Included monthly usage / headline limits | Important capability notes |
|---|---:|---|---|
| Copilot Free | $0 | 2,000 code completions per month; limited AI-credit allowance (GitHub does not state a fixed numeric Free credit amount in the cited plan/billing pages) | Auto model selection only; limited feature access; no Copilot cloud agent access |
| Copilot Pro | $10/month | 1,000 base + 500 flex = 1,500 AI credits | Model selection; cloud agent and code review access, subject to current feature/policy availability |
| Copilot Pro+ | $39/month | 3,900 base + 3,100 flex = 7,000 AI credits | Broader premium-model access and higher allowance |
| Copilot Max | $100/month | 10,000 base + 10,000 flex = 20,000 AI credits | Highest individual allowance and priority access to premium models/features |

**Free-plan details**
- Free is intended for eligible individual developers who do not have Copilot access through an organisation or enterprise.
- Inline code completions are capped at 2,000 per month.
- Free model access is through automatic model selection; users do not get the paid-plan model picker.
- GitHub's plan documentation says Free users can use Copilot Chat on GitHub.com and GitHub Mobile, and that cloud agent access requires a paid plan.
- Free has a limited AI-credit allowance, but the official plan and billing pages reviewed for this document do not publish a fixed numeric amount. Do not invent a chat-request count or promise a fixed number of agent tasks.
- Free is not unlimited code completion, unlimited chat, or an unlimited autonomous coding agent.

## 3. Organisation plans

| Plan | Published price | Monthly AI credits | Billing model |
|---|---:|---:|---|
| Copilot Business | $19 per granted seat | 1,900 per user | Per-seat subscription; credits pooled at the billing entity level |
| Copilot Enterprise | $39 per granted seat | 3,900 per user | Per-seat subscription; credits pooled at the billing entity level |

Organisation/enterprise policies control which models and features members can use. Usage beyond the included pool can be billed separately. GitHub also documents an enterprise Copilot access option with no included AI-credit allowance and metered usage; it is not the same as the standard Business/Enterprise included-credit plans.

## 4. What consumes usage

GitHub AI Credits are usage-based, not a simple fixed number of prompts.

- **1 AI credit = US$0.01.**
- Model interactions are priced by input, output and cached tokens.
- Model choice, prompt/context size, response length and agent activity affect consumption.
- Copilot Chat, Copilot CLI, Copilot cloud agent, Copilot Spaces, Spark and third-party coding agents can consume AI credits.
- Agent workflows can make multiple model calls during one task, so a multi-file repository task can cost substantially more than a short chat.
- Code completions and next-edit suggestions are accounted for separately from AI credits. Paid-plan completions are unlimited; Free has the 2,000/month completion limit.
- Included monthly credits do not roll over. GitHub says the allowance resets at 00:00 UTC on the first day of each calendar month.
- When an individual plan's included credits are exhausted, the user can wait for reset, upgrade, or enable additional paid usage with a budget. Additional usage is not free.
- For paid individual plans, GitHub documents a 10% model-cost discount for Auto model selection in Copilot Chat/cloud agent. Temporary promotions and model prices can change; consult the live billing pages.

**Cost control:** Keep additional paid usage disabled or set the additional-usage budget to US$0 and enable stop-at-budget if the intention is to avoid unexpected charges. Verify the account's billing settings rather than relying on a repository setting.

## 5. How the team should use Copilot

Copilot can be assigned bounded tasks alongside the existing development workflow:

1. **Inspect / explain:** map a module, trace a request, explain existing code and identify dependencies before editing.
2. **Implement:** make a focused change on a feature branch; avoid unrelated refactors.
3. **Test:** propose and run relevant tests where the environment supports it; report exact commands and results.
4. **Audit:** review its own diff and identify possible regressions, security issues and missing tests. A Copilot review is advisory, not an independent sign-off.
5. **Document:** update the canonical documentation with implementation changes.
6. **PR:** prepare a clear PR summary and evidence. Required GitHub Actions checks and human review remain mandatory.

Suggested delegation: use Copilot for bounded implementation, test scaffolding, explanations and first-pass review. The project technical lead coordinates architecture and task boundaries. The designated database author and owner approval process remain unchanged.

## 6. Mandatory repository and production safeguards

Copilot must follow `AGENTS.md`, the relevant canonical documents and this repository policy.

- Start from the latest `main` and work on a focused feature branch. Never push directly to `main`.
- Do not merge a PR, bypass branch protection, change rulesets, or deploy to production.
- Do not treat generated code as trusted. Review the complete diff, tests, dependencies and security implications.
- Never expose, paste, commit or ask Copilot to print secrets, access tokens, passwords, private keys, database URLs, production `.env` values or customer/payment personal data.
- Do not grant broader repository, organisation, cloud, terminal or MCP permissions than the task requires. Review agent tool permissions before approving execution.
- Never run destructive commands, production SQL, migration application, data deletion, secret rotation, infrastructure changes or production deployment through Copilot without the explicit owner-controlled process.
- **Database and schema:** Copilot may explain existing schema and suggest a draft for review, but it is not authorised by this document to author, renumber, edit, rename, delete or reformat protected/historical migrations, change the required migration manifest, modify the runner, apply production migrations or alter production data. Follow `docs/DATABASE_CHANGE_RULES.md` and `CLAUDE.md`; designated database authorship and owner approval remain in force.
- Preserve backend `127.0.0.1:8001`, PostgreSQL `5432`, database `sb_app`, API prefix `/api`, existing AWS/Amplify hosting and existing service/timer arrangement unless the owner approves a verified change.
- Do not claim tests, builds, deployments or runtime verification passed unless they actually ran. Record the exact commit and CI run.
- Copilot output, code review and explanations do not replace required CI, security review, owner review or production verification.

## 7. Plan and integration verification still required

The repository's use of Copilot has been reported by the project owner, but this documentation change does not inspect the contributor's private billing page or prove which subscription is active.

Before relying on cloud agent, agent mode, model selection, code review or higher limits, the account owner should verify:
- the assigned plan (Free, Pro, Pro+, Max, Business or Enterprise);
- the account's current monthly AI-credit allowance and remaining balance;
- whether Copilot is assigned individually or through an organisation;
- whether cloud agent, agent mode, code review, models and MCP are enabled for this account/repository;
- whether additional paid usage is enabled and what budget/stop policy applies;
- the repository's installed Copilot instructions and the actual permissions granted to the agent.

Plan and feature eligibility can change. Check the live official pages below before changing subscription or relying on a capability.

## 8. Official references

- [GitHub Copilot plans and feature comparison](https://docs.github.com/en/copilot/get-started/plans)
- [Usage-based billing for individuals](https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing)
- [Usage-based billing for organisations and enterprises](https://docs.github.com/copilot/concepts/billing/usage-based-billing-for-organizations-and-enterprises)
- [Models and pricing](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing)
- [GitHub Copilot code review](https://docs.github.com/copilot/concepts/agents/code-review)
- [GitHub Copilot custom instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)

---

**Maintenance:** Recheck this document whenever GitHub changes Copilot plan names, pricing, AI-credit allowances, model multipliers, agent eligibility or billing rules. Keep the research date and account-verification status explicit.
