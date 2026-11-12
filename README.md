# Super Bajaar

**Retail commerce, omnichannel operations and business management platform**

Super Bajaar is a React/Vite and FastAPI application backed by PostgreSQL. The repository contains the customer-facing application entry point, the operational/admin workspace, backend APIs, versioned database schema files and deployment-support scripts. GitHub Actions automation was removed by PR #77; do not assume repository CI/deployment workflows remain active.

This README describes the code currently committed on `main`. It is an engineering guide, not a claim that every module is complete or that the latest code is deployed to production.

## Engineering documentation

- [Production governance and readiness](docs/PRODUCTION_GOVERNANCE_AND_READINESS.md) — current owner decisions, IAM/self-approval risk, migration 045, deployment rollback, backup posture and open checks.
- [Documentation index](docs/README.md) — canonical document catalogue and precedence rules.
- [Environments and CI/CD](docs/ENVIRONMENTS_AND_CICD.md) — local, CI and production contexts; commit triggers; frontend/backend/database release separation.
- [Database migration operations](docs/DATABASE_MIGRATIONS.md) — migration runner, backup gate, numbering and production controls.
- [Production deployment runbook](docs/operations/PRODUCTION_DEPLOYMENT.md) — EC2/SSM and Amplify release verification.


- **Repository:** [siinghniibandhan-wq/superbajaar](https://github.com/siinghniibandhan-wq/superbajaar)
- **Default branch:** `main`
- **Canonical frontend application:** `frontend/`
- **Backend application:** `backend/app/`
- **Database schema migrations:** `backend/schema/`
- **Required schema release gate:** `backend/schema_required.txt`

The root Vite project is retained as a compatibility entry point. In particular, `src/App.jsx` re-exports the canonical app from `frontend/src/app/App.jsx`; it is not a second independent application implementation. Keep the two package/build entry points working unless an approved architecture change says otherwise.

## Product areas

### Unified Identity System

The Unified Identity System implementation is merged into `main` through PRs [#54](https://github.com/siinghniibandhan-wq/superbajaar/pull/54), [#55](https://github.com/siinghniibandhan-wq/superbajaar/pull/55), [#57](https://github.com/siinghniibandhan-wq/superbajaar/pull/57) and [#58](https://github.com/siinghniibandhan-wq/superbajaar/pull/58). It introduces permanent SBIDs for individual and organisation parties, typed profile links, identity register/review workflows, manual legacy reconciliation preview, customer claim history and cancellation, administrator-reviewed contact verification, organisation relationship lifecycle controls, and loyalty/referral association tables. Existing customer/staff authentication IDs and business-domain primary keys remain authoritative. This is a code-merged status. As reported and verified by the owner on 12 November 2026, migration 045 is applied (ledger count 41; checksum recorded in the production governance guide). Production deployment of the identity application and legacy data reconciliation remain separate verification items.

Read the [Unified Identity System implementation and operations guide](docs/UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md) and the [production rollout runbook](docs/UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md).


The current frontend source contains workspaces for:

- Catalogue
- Inventory
- Purchasing
- Point of Sale (POS)
- Customers and CRM
- Orders
- Payments
- Fulfilment
- Delivery
- Pricing
- Loyalty
- HR
- Accounting
- Reports
- Settings
- Master dashboard and shared overview components

The backend registers API routers for health, catalogue, inventory, inventory locations, orders, payments and Razorpay webhooks, delivery, fulfilment, customers, purchasing, purchasing lifecycle, HR, staff authentication, customer authentication, loyalty, accounting, organisation policies, pricing, POS and reports.

A directory, screen, API router or migration existing in Git does **not** prove that its business workflow is complete. Readiness must be established with API, database, permission and end-to-end evidence. In particular, test cross-module flows rather than marking a module complete from its UI alone.

### HR & Payroll implementation notes

The current HR workspace includes employee self-service routing for staff, itemised payslips, CSV payslip registers, browser print-to-PDF payslips, effective-dated salary revisions with manager review, approved overtime/incentive/bonus and arrears/final-settlement earning components, establishment-scoped payroll accrual journals, and a statutory remittance reconciliation CSV.

Important boundaries:

- Salary revisions and payroll earnings use approval workflows; variable earnings are included only after approval.
- The current payroll engine works on full calendar-month periods. Salary revisions and variable earning entries are therefore aligned to month boundaries.
- Gratuity, leave encashment, notice pay and other final-settlement amounts are manager-entered, reasoned and approved components. The application does **not** assume a legal eligibility test or calculate a statutory gratuity/leave-encashment formula automatically. HR/CA review remains necessary.
- Multi-establishment accruals are posted separately per legal establishment. Each establishment still needs approved Accounting event-to-account mappings; missing mappings are recorded as posting exceptions and must be corrected/retried.
- The statutory CSV is a reconciliation register, not a prescribed EPFO/ESIC/state portal return or filing confirmation.
- Employee bank-payment exports and employee document uploads are not enabled yet. They require encrypted sensitive-data storage, audited access and bank-specific payment-file specifications; do not add plaintext bank/PAN/Aadhaar data to ordinary employee records.
- Migrations 037 through 040 are committed and required by this application code. Their presence in Git does not mean they have been applied to production.

## Architecture

```text
Browser
  |
  v
React 18 + Vite
  frontend/src/app, frontend/src/features, frontend/src/services
  |
  v
FastAPI application
  backend/app/main.py
  |
  +--> API routers
  +--> authentication/session middleware
  +--> services and repositories
  +--> configured external integrations
  |
  v
PostgreSQL
  backend/schema/*.sql
  backend/scripts/apply_schema.sh
```

- **Frontend:** React 18, Vite 6 and `lucide-react`.
- **Backend:** Python FastAPI, Pydantic Settings and Psycopg.
- **Database engine:** PostgreSQL.
- **Live production database (observed 10 November 2026):** database name `superbajaar`, host `127.0.0.1`, port `5432`, application role `superbajaar_app`. This is the database configured by the live backend service at the time of verification; confirm the server configuration before any future infrastructure change.
- **Historical name only:** `sb_app` appears in older repository/default configuration and as the source database named in the baseline SQL's provenance comments. It is **not** the confirmed live production database.
- **Migration runner safety:** `backend/scripts/apply_schema.sh` currently defaults to `sb_app` when `SB_DB` is unset. Every production invocation or scheduled service must explicitly set `SB_DB=superbajaar`. Never rely on the runner default.
- **Backend ASGI entry point:** `backend/app/main.py`.
- **Compatibility ASGI entry point:** `backend/main.py` imports and exposes the canonical `app.main:app`.
- **API prefix:** `/api` by default.
- **Backend port setting:** `8001` by default; the actual runtime binding must match the process manager and reverse proxy configuration.
- **Payment integration:** Razorpay configuration is supported through backend environment settings. Use test credentials until the integration has been verified.

The repository includes AWS-related configuration fields and historical deployment assumptions, but this README does not assert the current state of any AWS account, EC2 instance, database, DNS record, CDN or production deployment. Verify live infrastructure independently before changing it.

## Repository layout

```text
superbajaar/
├── .github/
│   └── workflows/                 # CI, browser quality, DB checks and security scans
├── backend/
│   ├── app/
│   │   ├── api/                   # FastAPI route modules
│   │   ├── core/                  # Settings and authentication middleware
│   │   ├── integrations/           # External integrations
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/              # Business logic
│   │   └── middleware/
│   ├── schema/                    # Numbered PostgreSQL schema SQL files
│   ├── scripts/                   # Migration runner, integrity checks and tests
│   ├── tests/                     # Backend tests
│   ├── .env.example
│   ├── main.py                    # ASGI compatibility entry point
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── scripts/                   # Build and route validation helpers
│   ├── src/
│   │   ├── app/                   # Application shell and routing
│   │   ├── features/              # Business workspaces
│   │   ├── services/              # API helpers
│   │   └── styles.css
│   ├── tests/
│   │   ├── contracts/
│   │   ├── e2e/
│   │   └── unit/
│   ├── package.json
│   └── vite.config.js
├── src/                           # Root compatibility entry point
├── public/                        # Root public assets
├── index.html
├── package.json                   # Root compatibility build scripts
├── vite.config.js
├── README.md
└── SECURITY.md
```

This is an orientation map; the Git tree is authoritative for the exact file inventory.

## Local development

Use Node.js 20 for the frontend workflows, matching the CI configuration. Use Python 3.12 for backend CI and a compatible local Python environment.

### Frontend (canonical application)

```bash
cd frontend
npm install
npm run dev
```

The development server is configured for port `5173`.

Build the production bundle:

```bash
npm run build
```

Run frontend unit and contract tests:

```bash
npm run test:unit
```

Check admin navigation routes:

```bash
npm run test:routes
```

Run Playwright browser tests (after installing the Playwright browser dependencies):

```bash
npx playwright install --with-deps chromium
npm run test:e2e
```

### Root compatibility build

The root package also has Vite `dev`, `build` and `preview` scripts. CI builds both the root project and `frontend/`; keep both builds healthy.

```bash
npm install
npm run build
```

### Backend

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment, then install dependencies:

```bash
pip install -r requirements.txt
```

Configure the environment using `backend/.env.example` as a template. Start the canonical ASGI application from the backend directory:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The compatibility import `main:app` is also retained for existing process-manager commands. Do not change a deployed service command or port without checking the live service configuration first.

Run backend tests against a disposable test database:

```bash
cd backend
python -m pytest tests/test_*.py -q --strict-markers --strict-config
```

Never point local tests or migration experiments at production.

## Environment and secrets

The backend reads settings from environment variables and a local `.env` file. Start with `backend/.env.example`; replace placeholders with local/test values.

Important settings include:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed browser origins |
| `APP_ENV` | Runtime environment |
| `APP_NAME` | API display name |
| `API_PREFIX` | API route prefix; defaults to `/api` |
| `PORT` | Backend port; defaults to `8001` |
| `JWT_SECRET_KEY` | JWT signing secret; `SB_SECRET_KEY` is a compatibility fallback |
| `RAZORPAY_KEY_ID` | Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay API secret |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay webhook verification secret |
| `SB_SERVICEABLE_PINS` | Optional serviceability configuration |

Security rules:

- Never commit real `.env` files, passwords, API keys, signing keys, tokens, private keys or database credentials.
- Use a randomly generated signing secret of at least 32 characters; do not use the example placeholder.
- Treat every `VITE_*` variable as public because it can be embedded in the browser bundle. Never put server secrets in frontend variables.
- Use separate credentials and databases for development, tests and production.
- Grant the application database role only the permissions it needs.
- Do not log passwords, access tokens, payment secrets or unnecessary customer personal data.

## PostgreSQL schema and SQL migration numbering

> **Critical:** Never rename, edit, move or delete an existing migration file. Read [the migration filename immutability rule](docs/SCHEMA_MIGRATION_CRITICAL_RULE.md) before changing `backend/schema/`.
>
> Operational procedures, production database identity, status-only scheduling, manual apply steps and the historical duplicate-`036` reconciliation are documented in [Database Migrations](docs/DATABASE_MIGRATIONS.md).

**All versioned application schema SQL files belong in `backend/schema/`.** Do not place new application migrations in a miscellaneous folder or execute SQL merely because a file exists in the repository.

### Numbering rule — duplicate numbering is resolved and guarded

The migration files use this exact filename format:

```text
NNN_lowercase_description.sql
```

Examples from the current schema directory:

```text
000_baseline_schema.sql
001_loyalty_programme.sql
008_product_category_assignments.sql
009_product_availability_delivery.sql
...
034_hr_scheduling_leave_lifecycle.sql
035_inventory_facility_internal_locations.sql
036_configurable_rbac.sql
037_hr_salary_revision_history.sql
038_hr_variable_payroll_earnings.sql
039_hr_multi_establishment_payroll_accruals.sql
040_hr_final_settlement_earning_types.sql
041_portal_access_foundation.sql
042_hr_attendance_controls.sql
043_unified_identity_foundation.sql
044_identity_loyalty_referral_links.sql
045_identity_claim_cancellation_event.sql
```

The current committed schema directory contains **40 SQL files** (through `045_identity_claim_cancellation_event.sql`), with unique three-digit numeric prefixes. The numbering is not required to be consecutive: gaps are intentional historical/versioning space and must not be filled by renumbering existing files.

The previous duplicate-prefix problem has been addressed in the current migration set. Duplicate numbering is also actively rejected by the migration tooling and CI:

1. `backend/scripts/apply_schema.sh` validates every filename and stops if two files share the same three-digit prefix. It exits before taking a backup or applying SQL when a duplicate is found.
2. `.github/workflows/migration-check.yml` checks the filename format and prefix uniqueness on pull requests and pushes.
3. The migration-check workflow applies every schema file to disposable PostgreSQL 15 and 16 databases, then applies them again to check repeatability.
4. The migration runner has dedicated tests proving that duplicate prefixes (including duplicate `001` and `008`) are rejected before backup or SQL execution.

**When adding a migration:**

- Inspect the complete current `backend/schema/` directory and the history on the target branch first.
- Select a new, unused three-digit prefix. The current highest committed prefix is `045`; choose the next unused prefix only after checking the complete directory, branch history and migration governance checks.
- Never reuse a prefix, rename or renumber an already-applied migration, or edit an applied migration to change its effect. Create a new numbered migration for a later correction.
- Use lowercase letters, digits and underscores after the prefix.
- Keep SQL files focused on database schema/data changes. Do not put shell commands, deployment tooling, CI configuration or service-management changes inside SQL.
- Add a filename to `backend/schema_required.txt` in the same change when application code depends on the tables/columns it introduces and the release must be blocked until that migration is applied.
- Test the SQL against disposable PostgreSQL before proposing deployment.

### Required migration list

`backend/schema_required.txt` is the release-critical subset of schema files. It is **not** a complete inventory of every SQL file. Every name in that list must exist in `backend/schema/`. The migration runner uses it to decide whether a release may proceed when a non-required migration has failed. The current list explicitly documents why `011_customer_phone_uniqueness.sql` is not in that required subset; do not change that policy casually.

### Migration runner safeguards

Use the existing runner and its documented modes:

```bash
# Production target (use only when explicitly authorized):
SB_DB=superbajaar backend/scripts/apply_schema.sh backend/schema --dry-run
SB_DB=superbajaar backend/scripts/apply_schema.sh backend/schema --status
```

For local development or testing, set `SB_DB` to the explicitly provisioned disposable/local database name instead; do not copy the production value blindly.

The runner is designed to:

- Verify a PostgreSQL connection and migration filenames before proceeding.
- Reject duplicate migration prefixes and duplicate table names across non-system schemas.
- Refuse to guess when a populated database has no migration ledger.
- Take and verify a `pg_dump` backup before applying pending files; if backup verification fails, it makes no schema change.
- Apply each SQL file in its own transaction.
- Record applied filenames and SHA-256 checksums in `schema_migrations`.
- Record failures in `schema_migration_failures`, report them and avoid repeatedly retrying unchanged failed files.
- Detect edits to already-applied migrations and report them rather than silently reapplying them.
- Use `schema_required.txt` to distinguish a release-blocking migration failure from a non-required failure.

The `--dry-run` and `--status` modes still connect to the configured database to inspect its state. Run them only against the intended environment. Do not run the apply mode against production without explicit approval, a verified backup, a reviewed migration plan and a recovery plan. Never fake migration-ledger entries or manually bypass the required-file gate.

The migration runner tests are in `backend/scripts/tests/test_apply_schema.sh`. They require a throw-away PostgreSQL database and explicitly refuse configurations that look like production.

## CI, quality and security checks

GitHub Actions currently defines these workflows:

| Workflow | What it checks |
|---|---|
| Super Bajaar CI | Backend tests on PostgreSQL 15, frontend unit/contract tests, route validation and builds for both frontend entry points |
| Browser quality (Playwright + Lighthouse) | Frontend build, Playwright browser tests, and Lighthouse performance/accessibility/best-practices/SEO reports |
| Database files check | SQL filename and unique-number checks, schema integrity, repeatable PostgreSQL 15/16 application, permissions, migration-runner tests and backend database tests |
| Semgrep SAST | Static application security analysis |
| Gitleaks Secret Scan | Secret scanning |

The database workflow uses disposable CI databases; it does not apply migrations to the production database. CI success is evidence for the checks that actually ran, not proof of production deployment or of every real-world business workflow.

There are no current GitHub Actions runs for the deleted workflows. Do not report these checks as passing or active. Any replacement checks must be run manually or through a separately approved system and documented with actual evidence.

## Change and release discipline

**Current production trigger boundary:** The former GitHub Actions backend deployment and production database migration workflows were deleted by PR #77. They must not be described as active triggers. AWS Amplify's native Git integration is independent and may continue to publish frontend changes if its repository connection and auto-build settings remain enabled; verify those settings in Amplify. Backend deployment and database migration require their own separately verified AWS-side mechanisms. A commit to `main` alone is not proof that either has deployed or applied.


1. Read the existing implementation and relevant tests before editing.
2. Keep changes scoped and preserve existing screens, forms, state, API calls, buttons, routes and business workflows unless a change is explicitly approved.
3. Preserve storefront behaviour and existing category structure when working on admin modules.
4. Do not alter database deployment automation as a side effect of an application change.
5. Add or update tests for behaviour changes and update documentation when architecture, setup or operational rules change.
6. Review the complete diff for unintended deletions, generated files, secrets and duplicate SQL prefixes.
7. Run the relevant focused checks, then the applicable full CI checks.
8. State exactly what changed, which commit contains it, and which checks were actually run.
9. Treat deployment, production database migration and infrastructure modification as separate controlled operations. A code commit does not mean production has changed.

## Operational and data safety

- Never drop, reset, truncate, recreate or bulk-delete production data as a routine fix.
- Do not change AWS resources, DNS, security groups, service ports, reverse-proxy routing, secrets or production services without explicit authorization and a verified plan.
- Back up and verify data before any approved production database change.
- Keep customer and employee data confidential and apply least-privilege access.
- Follow the repository's `SECURITY.md` process for reporting vulnerabilities.

## Project status language

Use precise status labels:

- **Present in source:** the file or code exists in the repository.
- **Builds:** the relevant build command completed successfully.
- **Tested:** named tests ran and passed in the stated environment.
- **Integrated:** the end-to-end workflow across its dependent modules was verified.
- **Deployed:** the intended release is confirmed running in the target environment.
- **Production-ready:** security, data integrity, monitoring, backup/recovery and operational acceptance have been verified.

Do not use these labels interchangeably.
