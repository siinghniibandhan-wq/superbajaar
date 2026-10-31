# GitHub Copilot — optional Codespaces assistant policy

> **Status — 31 October 2026:** Copilot is removed from Super Bajaar's active issue-assignment and cloud-agent workflow. It may be used only as an optional coding assistant inside Codespaces when the owner explicitly invokes it and Codespaces usage is available.

## 1. Current account and usage position

- The owner's screenshots show a **GitHub Copilot Free** account.
- The Copilot features page shows **Copilot in the cloud — Coming soon**. The displayed “Enabled” status for other Copilot features does not establish that GitHub Coding Agent can be assigned issues.
- The owner reports that the **Codespaces usage limit is exhausted**. Therefore, no Copilot-in-Codespaces coding work can currently start.
- Do not upgrade Copilot, enable paid overage, top up Codespaces or incur billable compute without explicit owner approval.
- Copilot's own AI-credit balance and Codespaces compute allowance are separate. Do not conflate them.

## 2. Permitted use when Codespaces becomes available

Copilot may assist interactively inside a Codespace with inline code suggestions, explanations, debugging, bounded implementation assistance, test suggestions and documentation assistance.

Copilot is **not** an accountable GitHub issue owner, issue-pull or acknowledgement agent, cloud coding-agent executor or PR automation fallback. It does not replace ChatGPT's CTO/implementation coordination, Gemini's independent audit, Claude's designated database role or Perplexity's research role.

Any Copilot-assisted change must follow `AGENTS.md`, `.github/copilot-instructions.md`, the issue's scope and path reservations, feature-branch rules, review requirements, database safeguards and owner approval gates.

## 3. Current team ownership

- **ChatGPT:** CTO, architecture, bounded application implementation, coordination, integration, PR review and CI evidence review.
- **Gemini:** independent read-only audit and separately assigned non-schema fixes on reserved paths.
- **Claude:** complex backend/data-integrity engineering and designated SQL/schema/migration/runner authorship under `CLAUDE.md`.
- **Perplexity:** external research, official documentation, vendor/API verification and Indian compliance research.
- **Copilot:** optional in-Codespaces coding assistant only, subject to available usage and explicit owner invocation.
- **GitHub Actions:** deterministic CI/testing/security checks; not an AI task owner.

## 4. Safety and spending controls

No direct push to `main`, self-merge, branch-protection bypass, production data, secrets, destructive commands, production SQL, migration application, infrastructure or permission changes. Claude remains the designated SQL/schema/migration/runner author. Preserve the existing backend, database, API and hosting architecture unless the owner approves a verified change. Do not install services, upgrade plans or incur paid usage without approval. Report exact files, commands/tests, commit SHA, CI evidence and unverified items.

## 5. Reassessment

Reconsider Copilot's role only when the owner confirms Codespaces usage has reset or otherwise become available. Any proposed GitHub Copilot cloud-agent use requires a separate owner decision and fresh verification. Until then, no `agent:copilot` issue label, task assignment, acknowledgement timer or cloud-agent dispatch is part of the active workflow.
