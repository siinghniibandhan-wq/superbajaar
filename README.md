# Super Bajaar

**Omnichannel commerce, retail operations and business management platform**

Super Bajaar is a commerce platform intended to support the customer-facing storefront and the operational systems behind a retail business. This repository is the source of truth for application code, backend services, database schema, engineering documentation and CI workflows.

> [!IMPORTANT]
> This repository is being restored from the project checkpoint archive. A file appearing in the repository does not by itself prove that its feature is complete, tested, deployed or production-ready. Treat restoration, code verification, integration testing and deployment as separate milestones.

> [!CAUTION]
> Never reset, drop, truncate, recreate or bulk-delete production data. Do not change production infrastructure, service ports, API routing, deployment mechanisms, secrets or database migration automation without explicit owner approval and a verified plan.

## Project scope

The platform's intended business areas include:

- **Commerce:** storefront, catalogue, product attributes and variants, pricing, promotions, cart, checkout and orders.
- **Retail operations:** inventory, purchasing, goods receipt, batch and expiry tracking, stock ledger, reservations, fulfilment and delivery.
- **Customer operations:** customer profiles, CRM, support cases and loyalty.
- **Point of sale:** in-store POS and omnichannel sales visibility.
- **Finance:** payments, refunds, accounting, tax and financial reporting.
- **People and administration:** HR, payroll, roles, permissions and operational dashboards.

A module's presence in the project scope is not a completion claim. Verify its implementation, API contract, permissions, data integrity and end-to-end workflows before marking it ready.

## Repository layout

The checkpoint uses two frontend entry areas: the root-level Vite application and the separately organised `frontend/` application. Preserve their paths as supplied by the checkpoint; do not flatten or merge them without an explicit architecture decision.

```text
superbajaar/
├── .github/                 # GitHub workflows, dependency and PR configuration
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI route modules
│   │   ├── core/            # Settings, security and shared backend core
│   │   ├── integrations/    # External service integrations
│   │   ├── middleware/      # Request middleware
│   │   ├── models/          # Persistence/domain models
│   │   ├── repositories/    # Data access
│   │   ├── schemas/         # Request/response schemas
│   │   ├── services/        # Business logic
│   │   └── utils/           # Shared backend utilities
│   ├── schema/              # Versioned database schema migrations
│   ├── scripts/             # Operational and migration scripts
│   ├── tests/               # Backend tests
│   ├── main.py              # ASGI application entry point
│   └── requirements.txt
├── database/                # Database baseline and seed assets
├── docs/                    # Architecture, governance, plans and module records
├── frontend/
│   ├── public/              # Frontend static assets
│   ├── scripts/             # Frontend validation/build helpers
│   ├── src/
│   │   ├── app/             # Application shell and routing
│   │   ├── features/        # Business workspaces and feature modules
│   │   └── services/        # API and shared frontend services
│   ├── tests/               # Frontend and browser tests
│   ├── package.json
│   └── vite.config.js
├── public/                  # Root application public assets
├── src/                     # Root application entry and compatibility layer
├── index.html
├── package.json
├── vite.config.js
├── AGENTS.md                # Agent contribution guidance
├── CLAUDE.md                # Database/backend specialist guidance
├── GEMINI.md                # Contributor guidance
├── IMPORTANT_UPDATES.md     # Dated project decisions and status
├── SECURITY.md              # Security reporting and handling
└── README.md                # Project entry point
```

The precise file inventory is defined by the checkpoint and Git tree. This diagram is an orientation guide, not a replacement for inspecting the actual source paths.

## Architecture at a glance

The documented application architecture is:

1. React + Vite browser applications provide storefront and operational workspaces.
2. Frontend services call the backend through the configured API client.
3. Python FastAPI exposes API routes and validates requests, identity, permissions and business rules.
4. Repositories/services access PostgreSQL and any explicitly configured integrations.
5. Database changes are delivered through reviewed, versioned schema files and the existing migration runner.

The project checkpoint documents an AWS deployment arrangement involving Amplify for frontend hosting and EC2 with Nginx/Gunicorn for the backend. These are deployment records, not instructions to provision or modify infrastructure during source restoration. Confirm the live deployment configuration separately before making operational changes.

## Local development

Use the package manifest belonging to the application you intend to run. The repository contains both root-level and `frontend/` Vite configuration; do not assume they are interchangeable.

### Frontend workspace

```bash
cd frontend
npm install
npm run dev
```

Production build:

```bash
npm run build
```

### Backend

Use a supported Python version and an isolated virtual environment:

```bash
cd backend
python -m venv .venv
```

Activate the environment, then install the backend dependencies:

```bash
pip install -r requirements.txt
```

The application entry point is `backend/main.py`. Check the backend settings and environment example files before starting the service. Do not copy production secrets into local files or commit them.

> [!NOTE]
> These are setup commands, not a claim that dependencies have been installed or that the application currently builds. Run the actual checks and record their output before reporting a passing result.

## Configuration and secrets

- Use the supplied `.env.example` files as templates.
- Keep real `.env` files, API keys, database credentials, signing keys, tokens and production configuration out of Git.
- Never place privileged credentials in browser-exposed `VITE_*` variables. Any value compiled into a Vite frontend must be treated as public.
- Backend secrets belong in the approved runtime secret/configuration mechanism.
- Do not recreate or guess production credentials from historical documentation.

## Database and migration safety

Database schema changes must follow the project's database governance documents and existing runner contract.

- Add a uniquely numbered migration using the established naming convention in `backend/schema/`.
- Do not duplicate migration numbers or rewrite migrations already applied to an environment.
- Keep SQL migration files focused on schema/data changes; do not embed deployment-tooling changes in SQL.
- Review constraints, indexes, foreign keys, data migration impact and rollback/recovery implications.
- Run migration checks against disposable test databases before proposing a production change.
- Preserve the existing backup-before-change, per-file transaction, checksum ledger and failure-recording safeguards.
- A missing or unverified backup must stop a production schema change.
- Never manually fake migration-ledger entries or apply migrations to production without explicit approval.

Read `docs/DATABASE_CHANGE_RULES.md` and the runner documentation before changing database files.

## Engineering and release rules

1. Inspect the current source and relevant documentation before editing.
2. Keep changes narrowly scoped and preserve existing user-facing workflows, forms, state, API calls and business rules unless the owner explicitly approves a change.
3. Work on a feature branch from the latest `main`; use pull requests for review.
4. Include tests and update the relevant documentation with material changes.
5. Review the complete diff for unintended file changes, secrets, generated files and migration-number collisions.
6. Report exactly which checks ran and their actual results.
7. A successful build is not proof of end-to-end correctness.
8. Do not deploy, change AWS resources or alter production data as part of a code-only restoration task.

## Security baseline

- Enforce authentication and authorization on the backend; frontend route hiding is not access control.
- Validate all inputs and enforce business rules server-side.
- Restrict CORS to approved origins; do not use wildcard origins with credentialed requests.
- Apply rate limits to sensitive and abuse-prone endpoints.
- Keep privileged APIs and secrets out of browser bundles.
- Use parameterized database access and least-privilege database roles.
- Avoid logging passwords, tokens, payment data or unnecessary personal information.
- Review dependency alerts and run the repository's security checks where configured.
- Report security issues privately using the process in `SECURITY.md`.

## Documentation map

| Document | Purpose |
|---|---|
| `AGENTS.md` | General repository contribution and agent rules |
| `CLAUDE.md` | Specialist database/backend operating rules |
| `GEMINI.md` | Contributor instructions |
| `IMPORTANT_UPDATES.md` | Dated decisions and project updates |
| `SECURITY.md` | Security reporting and handling |
| `docs/architecture.md` | System architecture and API contracts |
| `docs/DEVELOPMENT_WORKFLOW.md` | Development, review and operations workflow |
| `docs/DATABASE_CHANGE_RULES.md` | Database governance and migration safeguards |
| `docs/AI_ENGINEERING_OPERATING_MODEL.md` | AI contributor roles and handoffs |
| `docs/MODULE_READINESS_AUDIT.md` | Module readiness evidence and gaps |
| `docs/ACCOUNTING_INTEGRATION_STATUS.md` | Accounting integration status record |

Consult the relevant detailed document rather than treating this README as the full technical specification.

## Current repository restoration status

The new repository is being populated from the archived checkpoint while preserving original paths and excluding transient caches and environment-specific secret/configuration files.

Restoration is complete only when:
- the expected source files and directory structure are present;
- the restored Git tree is compared against the checkpoint inventory;
- required environment templates and documentation are accounted for;
- frontend and backend checks have been run and their results recorded; and
- any missing or intentionally excluded files are documented.

Do not interpret a partial Git tree, this README, or a commit message as proof that the application is restored, tested or deployed.

---

**Project:** Super Bajaar  
**Repository:** [siinghniibandhan-wq/superbajaar](https://github.com/siinghniibandhan-wq/superbajaar)  
**Default branch:** `main`
