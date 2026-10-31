# Security and Governance Policy

## Purpose

This policy defines the independent technical, security, and change-review role assigned to KPMC Enterprises as a human collaborator on the Superbajaar repository. Superbajaar remains the product owner and retains business, product, release, and production decision authority.

## Roles and separation of duties

### Superbajaar repository owner / product owner

- Owns product direction, roadmap, business requirements, and acceptance criteria.
- Authorises production releases, infrastructure changes, production data operations, and changes to secrets or deployment configuration.
- Retains repository administration and final merge/release authority, subject to enforced repository rules.

### KPMC Enterprises — independent technical and security reviewer

- Reviews pull requests independently for correctness, maintainability, security, and consistency with approved architecture.
- Reviews authentication, authorisation, input validation, data exposure, dependency changes, and security-sensitive configuration.
- Reviews database migrations for additive/idempotent design, unique migration numbering, data integrity, rollback/recovery considerations, and compliance with the repository's database change rules.
- Checks relevant CI evidence, including backend tests, frontend builds, PostgreSQL compatibility checks, secret scanning, and static analysis.
- Records actionable review comments and approves only after material concerns are resolved.
- Reviews deployment-related code and release evidence, but does not deploy to production or change production infrastructure without explicit owner authorisation.

KPMC's collaborator status does not itself grant authority to change product scope, production systems, secrets, billing, customer data, or deployment settings.

## Required change-control process

1. All application, database, workflow, and configuration changes are proposed through a pull request targeting `main`.
2. Pull requests must describe purpose, scope, risks, affected modules, database/API impact, tests actually run, and release implications.
3. At least one eligible human approval from an independent reviewer is required before merging. The author must not approve their own pull request.
4. Required CI checks must pass on the exact proposed commit. Branches must be up to date with the base branch where required by repository rules.
5. Review conversations must be resolved before merge.
6. Material changes pushed after approval must trigger renewed review where repository settings require dismissal of stale approvals.
7. No direct pushes, force pushes, or deletion of `main`.
8. Merging and production deployment are separate decisions. A successful merge is not evidence of deployment or production verification.

## Database safeguards

- Follow `docs/DATABASE_CHANGE_RULES.md` and the repository's canonical database instructions.
- Never edit, rename, delete, or reformat an applied migration.
- New migrations must be additive, idempotent, uniquely numbered, and tested against the supported PostgreSQL versions as required by CI.
- Never run a production migration, alter production data, or change database ownership/permissions without explicit production-owner approval and a verified backup/recovery plan.

## Security controls

- Keep GitHub secret scanning / push protection and private vulnerability reporting enabled where supported by the repository plan and settings.
- Run Gitleaks and Semgrep on pull requests and protected-branch pushes.
- Keep Dependabot security updates and dependency review operational; review major-version updates separately.
- Use least-privilege GitHub and cloud permissions. Do not share personal tokens or credentials.
- Store secrets only in approved secret stores or GitHub Actions secrets; never commit secrets or production data.
- Report vulnerabilities privately using the repository's `SECURITY.md` process. Do not publish exploit details in public issues.

## Audit evidence

For each material change, retain the pull request, human review decision, CI run links/results, relevant migration/test evidence, and release approval. Do not claim a test, scan, backup, deployment, or production check passed unless it was actually executed and observed.

## Limits and review cadence

KPMC provides independent review and technical/security oversight as a collaborator; it is not a substitute for a qualified penetration test, legal/compliance assessment, or operational monitoring. Review repository access, branch rules, required checks, and security settings periodically and whenever responsibilities or personnel change.
