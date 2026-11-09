# GitHub Copilot — secondary coding agent policy

> **Status — 1 November 2026:** Copilot is retained as a secondary coding agent for optional bounded coding assistance when access and usage are available. It is explicitly excluded from all PR review and approval workflows.

## 1. Current account and usage position

- The owner's screenshots show a **GitHub Copilot Free** account.
- The Copilot features page shows **Copilot in the cloud — Coming soon**. The displayed “Enabled” status for other Copilot features does not establish that GitHub Coding Agent can be assigned issues.
- The owner reports that the **Codespaces usage limit is exhausted**. Therefore, no Copilot-in-Codespaces coding work can currently start.
- Do not upgrade Copilot, enable paid overage, top up Codespaces or incur billable compute without explicit owner approval.
- Copilot's own AI-credit balance and Codespaces compute allowance are separate. Do not conflate them.

## 2. Permitted use when Codespaces becomes available

Copilot may assist with inline code suggestions, explanations, debugging, bounded implementation assistance, test suggestions and documentation assistance when the relevant feature and usage are available.

Copilot is **not** a PR reviewer, formal approver, required reviewer, code-owner substitute, issue-dispatch agent or release gate. Do not enable Copilot code review, request Copilot reviews, treat its comments as approval or make review completion depend on Copilot. The active review group is the repository owner, ChatGPT and Perplexity; the owner alone gives formal GitHub approval. Claude retains the designated database role.

Any Copilot-assisted change must follow `AGENTS.md`, `.github/copilot-instructions.md`, the issue's scope and path reservations, feature-branch rules, database safeguards and owner approval gates. All Copilot-authored changes require review by ChatGPT and/or Perplexity as assigned; Copilot cannot review its own work.

## 3. Current team ownership

- **ChatGPT:** CTO, architecture, bounded application implementation, coordination, integration, PR review and CI evidence review.
- **Gemini:** independent read-only audit and separately assigned non-schema fixes on reserved paths.
- **Claude:** complex backend/data-integrity engineering and designated SQL/schema/migration/runner authorship under `CLAUDE.md`.
- **Perplexity:** external research, official documentation, vendor/API verification and Indian compliance research.
- **Copilot:** secondary coding agent for bounded coding assistance only; no PR review, approval, reviewer assignment or release gate.
- **GitHub Actions:** deterministic CI/testing/security checks; not an AI task owner.

## 4. Safety and spending controls

No direct push to `main`, self-merge, branch-protection bypass, production data, secrets, destructive commands, production SQL, migration application, infrastructure or permission changes. Claude remains the designated SQL/schema/migration/runner author. Preserve the existing backend, database, API and hosting architecture unless the owner approves a verified change. Do not install services, upgrade plans or incur paid usage without approval. Report exact files, commands/tests, commit SHA, CI evidence and unverified items.

## 5. Reassessment

Copilot may be used as a secondary coding agent when its coding features and usage are available; no plan upgrade or paid overage without owner approval. Any proposed cloud-agent use requires a separate owner decision and fresh verification. Copilot review remains disabled/excluded regardless of coding-agent availability.
