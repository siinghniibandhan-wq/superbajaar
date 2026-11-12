# Super Bajaar engineering documentation

**Documentation owner:** Engineering  
**Last reviewed:** 12 November 2026  
**Status:** Canonical documentation index

This directory contains current engineering references, operational runbooks, historical audit/design records, implementation plans and supporting configuration. Source code and workflow YAML define implemented behaviour; live infrastructure and deployment state require timestamped evidence.

## Start here

| Need | Canonical reference |
|---|---|
| Project overview, setup and repository map | [Repository README](../README.md) |
| Current production decisions, IAM approval model, self-approval, migration 045, backup evidence and open actions | [Production governance and readiness](PRODUCTION_GOVERNANCE_AND_READINESS.md) |
| Environment tiers, CI/CD triggers and release types | [Environments and CI/CD](ENVIRONMENTS_AND_CICD.md) |
| PostgreSQL migration policy, runner modes and production commands | [Database migrations](DATABASE_MIGRATIONS.md) |
| EC2 backend, Amplify deployment and rollback | [Production deployment runbook](operations/PRODUCTION_DEPLOYMENT.md) |
| Migration filename immutability | [Schema migration critical rule](SCHEMA_MIGRATION_CRITICAL_RULE.md) |
| Unified Identity implementation | [Identity implementation guide](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md) |
| Unified Identity production rollout | [Identity rollout runbook](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md) |

## Mandatory documentation change control

Every governed implementation or configuration change must include its corresponding documentation update in the same pull request. This includes application code, APIs, database schema/migrations, integrations, configuration, CI/CD, infrastructure automation, security controls and operational behaviour.

1. Identify the canonical documentation affected before implementation.
2. Update the architecture, API, module, database, deployment, security or operations guide in the same PR.
3. Update examples, environment variables, commands, diagrams, migration inventories, limitations and rollback/recovery instructions where relevant.
4. Record verification evidence and distinguish implemented, tested, merged, deployed and production-verified states.
5. Do not defer a required documentation change to a later PR. The Documentation governance check enforces a documentation file in the same PR for governed changes.
6. Documentation-only changes do not require artificial code changes.

## Documentation catalogue

### Current operational references
- [Production governance and readiness](PRODUCTION_GOVERNANCE_AND_READINESS.md) — canonical owner decisions, accepted risks, IAM boundaries, self-approval, migration 045, deployment rollback, backup posture and open verification.
- [Database migrations](DATABASE_MIGRATIONS.md) — migration runner, immutable numbering, backup gates and dated production evidence.
- [Environments and CI/CD](ENVIRONMENTS_AND_CICD.md) — local/CI/production distinctions, path filters, workflow responsibilities and release evidence.
- [Production deployment](operations/PRODUCTION_DEPLOYMENT.md) — EC2/SSM and Amplify deployment/recovery.
- [GitHub main auto-sync](operations/GITHUB_MAIN_AUTO_SYNC.md) — source synchronization behaviour; not a deployment.
- [Super Admin provisioning](operations/SUPER_ADMIN_PROVISIONING.md) — controlled administrator provisioning.
- [Vendor portal S3 storage](VENDOR_PORTAL_S3_STORAGE.md) — private document-storage design and rollout requirements.
- [Schema migration critical rule](SCHEMA_MIGRATION_CRITICAL_RULE.md) — immutable migration files and unique numbering.

### Unified Identity
- [Implementation guide](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md)
- [Production rollout runbook](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md)
- [Phase 1 audit](UNIFIED_IDENTITY_SYSTEM_PHASE_1_AUDIT.md) — historical audit evidence.
- [Phase 2 database architecture](UNIFIED_IDENTITY_SYSTEM_PHASE_2_DATABASE_ARCHITECTURE.md) — historical design record.

### Historical investigation, plans and specifications
- [Schema automator verification (10 Nov 2026)](operations/SCHEMA_AUTOMATOR_VERIFICATION_2026-11-10.md)
- [SQL schema automator findings](operations/SQL_SCHEMA_AUTOMATOR_FINDINGS.md)
- [HR & Payroll completion plan](plans/2026-11-11-hr-payroll-completion.md)
- [HR & Payroll completion design](specs/2026-11-11-hr-payroll-completion-design.md)
- [Amplify rollback IAM policy](operations/amplify-rollback-iam-policy.json) — policy template; verify placeholders and scope before use.

Historical audits and investigation logs are retained as evidence. They are not live dashboards: where an older dated statement conflicts with the canonical production governance guide, use the newer explicitly dated observation and re-verify before acting.

## Precedence and safety

1. Source code and workflow definitions determine implemented behaviour.
2. The production governance guide records owner decisions and the latest consolidated status.
3. Operational runbooks define procedures, subject to live preflight and separate approval.
4. Feature implementation guides describe scope and limitations.
5. Dated audits, plans and design documents remain historical evidence.

A documentation change is not authorization to deploy, apply SQL, restore a database, change IAM or modify production infrastructure.
