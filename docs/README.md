# Super Bajaar engineering documentation

**Documentation owner:** Engineering  
**Last reviewed:** 12 November 2026  
**Status:** Repository documentation index

This directory contains current engineering references, operational runbooks, historical audit/design records, implementation plans and supporting configuration. The GitHub workflows and application source are authoritative for implemented behaviour; operational state must be confirmed from live services and workflow evidence.

## Start here

| Need | Canonical reference |
|---|---|
| Project overview, setup and repository map | [README](../README.md) |
| Environment tiers, CI/CD triggers and release types | [Environments and CI/CD](ENVIRONMENTS_AND_CICD.md) |
| PostgreSQL migration policy, runner modes and production commands | [Database migrations](DATABASE_MIGRATIONS.md) |
| Production backend and Amplify deployment | [Production deployment runbook](operations/PRODUCTION_DEPLOYMENT.md) |
| Migration filename immutability | [Schema migration critical rule](SCHEMA_MIGRATION_CRITICAL_RULE.md) |
| Unified Identity current implementation | [Identity implementation guide](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md) |
| Unified Identity production rollout | [Identity rollout runbook](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md) |

## Documentation catalogue

### Architecture and implementation
- [Unified Identity implementation](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md) — current merged code scope, capabilities, limitations and outstanding verification.
- [Vendor portal S3 storage](VENDOR_PORTAL_S3_STORAGE.md) — vendor document-storage design and operational constraints.

### Database governance
- [Database migrations](DATABASE_MIGRATIONS.md) — canonical migration operations reference.
- [Schema migration critical rule](SCHEMA_MIGRATION_CRITICAL_RULE.md) — immutable migration files and numbering policy.

### Operations
- [Production deployment](operations/PRODUCTION_DEPLOYMENT.md) — EC2, SSM, Amplify and recovery workflow.
- [GitHub main auto-sync](operations/GITHUB_MAIN_AUTO_SYNC.md) — source synchronization behaviour.
- [Super Admin provisioning](operations/SUPER_ADMIN_PROVISIONING.md) — controlled administrator provisioning.
- [Schema automator verification (10 Nov 2026)](operations/SCHEMA_AUTOMATOR_VERIFICATION_2026-11-10.md) — dated verification evidence.
- [SQL schema automator findings](operations/SQL_SCHEMA_AUTOMATOR_FINDINGS.md) — historical findings and investigation record.
- [Amplify rollback IAM policy](operations/amplify-rollback-iam-policy.json) — supporting least-privilege policy document; review placeholders before use.

### Historical Unified Identity records
- [Phase 1 audit](UNIFIED_IDENTITY_SYSTEM_PHASE_1_AUDIT.md) — original baseline audit; superseded for current implementation status.
- [Phase 2 database architecture](UNIFIED_IDENTITY_SYSTEM_PHASE_2_DATABASE_ARCHITECTURE.md) — original target architecture; superseded for implementation status and current schema facts.
- [Production rollout](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md) — current controlled rollout runbook.

### Plans and specifications
- [HR & Payroll completion plan](plans/2026-11-11-hr-payroll-completion.md) — dated execution plan; consult current source and PR state before treating any task as open.
- [HR & Payroll completion design](specs/2026-11-11-hr-payroll-completion-design.md) — design decisions and acceptance scope for the HR & Payroll work.

## Document precedence and change control

When documents overlap, use this precedence:

1. Current source code and workflow definitions for implemented behaviour.
2. Current operational runbooks for approved procedures (subject to live preflight).
3. Current implementation guides for feature scope and limitations.
4. Dated audit reports, design specifications and plans as historical evidence.

Do not delete historical audit or design records merely because a newer implementation guide exists. Mark them as superseded and link to the canonical current reference. Merge only documents that repeat the same current procedure; preserve dated incident evidence and original design decisions.

Before changing production instructions, verify the live target, workflow trigger, protected environment, backup procedure and approval boundary. A documentation change is not operational authorization.
