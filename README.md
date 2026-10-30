# Super Bajaar

Super Bajaar is a commerce storefront and ERP application. This file is the single project guide: it explains the current structure, what each important file does, how requests flow, and how the application is deployed.

> [!CAUTION]
> **Production safety:** Never reset, drop, truncate, recreate or bulk-delete production data. Do not change the established AWS/EC2, Amplify, Nginx, Gunicorn, systemd, PostgreSQL, port or API-prefix arrangement without explicit approval and a verified plan. Never expose credentials or secrets in documentation, logs, commits or chat.

> [!WARNING]
> **Do not treat a visible screen, registered route, passing unit test or successful CI run as proof of a complete production workflow.** Verify the complete UI → API → permission/business rule → PostgreSQL → response path. CI scratch-database tests do not prove production database state, backup validity, live deployment or full business readiness.

> [!IMPORTANT]
> **Documentation rule:** Every new or changed API and every major architecture, module, database, security, integration, deployment or workflow change must update the relevant README section. Add a short dated entry to `IMPORTANT_UPDATES.md` in the same feature branch and pull request. Do not push directly to `main`.

## Project overview and current progress

### At a glance

| Layer | Current repository / deployment design |
|---|---|
| Customer and employee UI | React + Vite frontend |
| Frontend hosting | AWS Amplify |
| Backend API | FastAPI application |
| Backend hosting | AWS EC2 behind existing Nginx and Gunicorn |
| Backend listener | `127.0.0.1:8001` |
| Database | PostgreSQL, database `sb_app`, port `5432` |
| Public API prefix | `/api` |
| Source control | GitHub; protected `main`, feature branches and pull requests |
| Database change control | Versioned SQL files, safe migration runner, migration ledger and CI gates |

### Current project status — repository evidence, not a production certification

| Area | Current status | Evidence / qualification |
|---|---|---|
| Main-branch safety | <span>Protected workflow established</span> | PR #150 merged; branch ruleset requires PR and database checks |
| Database migration safety | CI verified on PostgreSQL 15 and 16 | PR #150 checks passed on disposable test databases; production DB was not changed or certified |
| Backend automated tests | Passed on PR #151 documentation head | GitHub check run for commit `af3b239` completed successfully |
| Frontend builds | Both configured build checks passed on PR #151 documentation head | GitHub Actions results; this is not a live browser or deployment test |
| Architecture / customer / admin / employee flows | Documented from current source | Diagrams describe implemented routes and explicitly label gaps; they are not end-to-end acceptance results |
| API coverage | Route inventory documented below | Route registration/source review only; each operation still needs request/response and database verification |
| Production DB / backup / migration ledger | **Not verified by these documentation PR checks** | Requires owner-approved, read-only production preflight |
| Production deployment and live checkout | **Not verified here** | Requires separately approved runtime and end-to-end checks |
| Manager/staff employee UI | **Incomplete in current frontend entry gate** | Current Admin Console frontend entry is limited to owner/admin |

> [!NOTE]
> **How to read progress:** “CI passed” means the named GitHub workflow checks passed for the cited commit. It does not mean the production service, database, payments, stock reservation, carrier tracking or all workspaces are production-ready. Update this table only when new evidence is available.

### Overall architecture at a glance

```mermaid
flowchart LR
    C["Customer browser"] --> WEB["React storefront<br/>AWS Amplify"]
    E["Owner / admin / employee browser"] --> ADMIN["React admin workspaces<br/>AWS Amplify"]
    WEB --> CLIENT["Shared API client"]
    ADMIN --> CLIENT
    CLIENT -->|"HTTPS /api/*"| NGINX["Nginx on AWS EC2"]
    NGINX -->|"127.0.0.1:8001"| FAST["Gunicorn + FastAPI"]
    FAST --> AUTH["Session authentication<br/>role checks + validation"]
    AUTH --> ROUTES["Domain API routers"]
    ROUTES --> DB[("PostgreSQL<br/>sb_app :5432")]
```


## PRECAUTIONS AND STRICTLY PROHIBITED CHANGES

This section is a mandatory safety checklist for every contributor and coding agent. A change that conflicts with these rules must stop for explicit approval; do not improvise, “clean up,” reset, replace, or bypass existing infrastructure.

### Runtime, ports, database and services — do not change casually

- Backend must continue to listen on **port `8001`**. Do not move it to `8000` or another port.
- PostgreSQL must continue to listen on **port `5432`**. Do not change the port or replace PostgreSQL with another database.
- Production database name is **`sb_app`** (verify the target before any database operation; never create a substitute database to avoid a connection problem).
- Preserve the existing **Gunicorn** backend process, its current bind address/port, and the existing **systemd service and timer** used for backend operation/code synchronization. Do not replace, rename, disable, or bypass these services or change their cadence without explicit approval.
- Preserve the existing **Nginx** reverse-proxy configuration and routing to the backend on `127.0.0.1:8001`. Do not change upstreams, proxy routes, TLS, or host configuration as a workaround without approval.
- Preserve the existing **AWS EC2 backend** and **AWS Amplify frontend** deployment arrangement. Do not create a new server, service, deployment target, database, or hosting platform without approval.
- Preserve the existing automatic deployment/synchronization mechanisms, repository/branch settings, build settings, environment-variable names, and deployment hooks. Do not disable, replace, or trigger production deployment merely to test a change. Confirm the exact workflow before editing deployment configuration.
- Keep the existing public API prefix `/api`, CORS/security configuration, authentication/session behaviour, and established frontend-to-backend URL contract unless a verified requirement and explicit approval authorize a change.
- Never print, commit, rotate, overwrite, or remove production secrets or environment values as part of unrelated work. Never put credentials in README or source code.

### Schema files and migration rules — strictly prohibited

- **Never edit, delete, rename, replace, regenerate, or reformat `backend/schema/000_baseline_schema.sql`.**
- **Never edit, delete, rename, replace, regenerate, or reformat `backend/schema/009_loyalty_programme.sql`.**
- Do not edit, delete, rename, reorder, or reapply `backend/schema/009_product_availability_delivery.sql` as a quick fix. It shares the `009` prefix with the protected loyalty migration; its production application status and migration-runner ordering must be verified first.
- Never edit or delete any existing migration that may already have been applied. Inspect all schema files and the target database's `schema_migrations` records before choosing the next unused migration number.
- If a schema change is truly necessary, create a separate additive, idempotent migration using the existing approved workflow. Follow the project’s one-new-schema-file rule; do not bundle unrelated schema changes.
- Never run `DROP TABLE`, `DROP SCHEMA`, `TRUNCATE`, destructive reset scripts, database recreation, or bulk-delete statements against production. Never assume a table is disposable because it is empty or absent from this README.
- Treat **all existing production tables, records, sequences, indexes, constraints, triggers, grants, and migration history as protected**. This includes, wherever present, products, categories, attributes, variants, product images, customers, users, user sessions, orders, payments, stock locations/balances/movements, suppliers/purchasing, deliveries/shipments, loyalty data, and `schema_migrations`.
- Do not change table ownership, database roles/permissions, or production data without an explicitly approved, verified migration plan and backup.
- A schema file being present in Git does not prove it has or has not been applied in AWS. Check the live migration ledger and database state before any decision that depends on application status.

### Source control, coding and verification — strictly required

- **Switch to the intended working branch first.** If branch switching fails, stop; do not pull, edit, build, test, or commit on the wrong branch.
- Create work branches from the current `main`; never push directly to `main`. Use a pull request and review its complete diff before merging.
- Do not overwrite or revert unrelated working code. Keep changes minimal and within the approved scope.
- Never claim a build, test, endpoint, database integration, or deployment passed unless it was actually executed and the result was observed. Distinguish local/Codespaces checks from live AWS verification.
- Before merging backend/schema changes, verify the frontend build, backend tests, route registration, migration compatibility, and relevant API/database behaviour. Do not deploy merely because unit tests pass.
- Do not run production migrations or deploy automatically as part of documentation or routine code changes.
- If any instruction in this section conflicts with a proposed change, stop and ask for approval rather than proceeding.

## Fixed technology and runtime

- Frontend: React + Vite, hosted on AWS Amplify.
- Backend: FastAPI on AWS EC2, behind the existing Nginx configuration.
- Database: PostgreSQL.
- Backend port: `8001` (keep unchanged).
- PostgreSQL port: `5432` (keep unchanged).
- Frontend development port: `5173` (existing Vite configuration).
- API prefix: `/api` (the only public API prefix).
- Do not add ports, services, databases, or deployment targets without an identified need and approval.
- Never reset or clear production data as part of routine development.

## Main request flow

1. A page or form in the frontend calls the shared frontend API client.
2. The API client sends an HTTP request to the backend URL with the required authentication token.
3. A route in `backend/app/api/` receives and validates the request.
4. Backend code applies the relevant business rules and checks permissions.
5. PostgreSQL is read or updated using the existing database connection/query code.
6. The backend returns a response; the frontend displays the result or error.

There must be one authoritative backend API system. Frontend API functions are callers, not a second backend. Frontend values must not be trusted for authoritative prices, tax, stock, permissions, or order totals.

## Frontend file map

- `frontend/package.json`: frontend dependencies and build scripts.
- `frontend/index.html`: Vite HTML entry.
- `frontend/vite.config.js`: Vite configuration; existing development port is `5173`, preview configuration is `4173`. Do not change these casually.
- `frontend/src/main.jsx`: React entry point.
- `frontend/src/app/`: application shell and routing.
- `frontend/src/pages/`: page-level UI.
- `frontend/src/features/`: feature/module-specific UI and workflows.
- `frontend/src/components/`: reusable UI components.
- `frontend/src/layouts/`: shared page layouts.
- `frontend/src/services/api.js`: shared frontend API request function, base URL, auth token header, response and error handling.
- `frontend/.env.example`: example frontend environment configuration. Production API URL must match the deployed backend; do not commit secrets.

## Backend file map

- `backend/requirements.txt`: Python dependencies.
- `backend/app/main.py`: creates the FastAPI application, middleware and registers routers.
- `backend/app/core/config.py`: environment-based settings, API prefix, CORS configuration and backend port setting.
- `backend/app/core/auth_middleware.py`: active-session/authentication middleware.
- `backend/app/api/auth.py`: authentication endpoints.
- `backend/app/api/catalogue.py`: catalogue, categories, product attributes and variants endpoints.
- `backend/app/api/inventory.py`: inventory endpoints.
- `backend/app/api/purchasing.py`: purchasing endpoints.
- `backend/app/api/orders.py`: order endpoints.
- `backend/app/api/payments.py`: payment endpoints.
- `backend/app/api/delivery.py`: delivery endpoints.
- `backend/app/api/customers.py`: customer endpoints.
- `backend/app/api/health.py`: health endpoint.
- `backend/tests/`: backend tests.

The route files on the current codebase include some direct database access. A separate service/repository layer is not assumed to exist everywhere. Extract code only when a verified fix or maintenance need justifies it; do not rewrite working modules just to match a folder pattern.

## Backend API endpoints currently registered

All paths below are prefixed with `/api` by `backend/app/main.py`. This list is based on route declarations in the repository, not a claim that production/database integration has been runtime-tested.

- Health: `GET /health`
- Authentication: `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`
- Catalogue: `GET/POST /catalogue/categories`, `GET/POST /catalogue/products`, `DELETE /catalogue/products/{product_id}` (owner/admin only; mandatory reason recorded in `product_deletion_audit`; blocked when operational records reference the product), `GET /catalogue/attributes`, `POST /catalogue/attributes`, `GET /catalogue/products/{product_id}/attributes`, `PUT /catalogue/products/{product_id}/attributes/{attribute_id}`, `GET/POST /catalogue/products/{product_id}/variants`, `GET/POST /catalogue/products/{product_id}/images`, `GET /catalogue/variants`, `PUT /catalogue/variants/{variant_id}/price`
- Inventory: `GET/POST /inventory/locations`, `GET /inventory/balances`, `GET /inventory/movements`, `POST /inventory/adjustments`
- Orders: `GET/POST /orders`, `GET /orders/summary`, `GET /orders/{order_id}`, `PATCH /orders/{order_id}/status`
- Payments: `GET/POST /payments`, `PATCH /payments/{payment_id}/status`
- Delivery: `GET/POST /delivery/shipments`, `PATCH /delivery/shipments/{shipment_id}/status`
- Customers and support: `GET/POST /customers`, `PATCH /customers/{customer_id}`, `GET/POST /customers/support-cases`, `PATCH /customers/support-cases/{case_id}`
- Purchasing: `GET/POST /purchasing/suppliers`, `GET/POST /purchasing/orders`, `GET /purchasing/orders/{purchase_id}`, `POST /purchasing/orders/{purchase_id}/receive`

Route existence does not prove that a screen works end to end. For each workspace, check the actual request payload, response fields, authentication and database schema. A missing operation must be implemented against the existing schema and tested; do not invent a second API or change ports to work around it.


### Product deletion and catalogue testing

- The Catalogue workspace shows **Delete** only to signed-in `owner` and `admin` users.
- Every deletion requires a reason of at least 10 characters and a second confirmation.
- The backend independently enforces the owner/admin role; hiding the button is not the security boundary.
- A durable audit row records product ID/name/slug, reason, operator ID/email/role and timestamp.
- Deletion and audit insertion run in one database transaction. If foreign-key references from orders, inventory or other operational records prevent deletion, the transaction rolls back and the API returns HTTP 409; use Archive instead.
- This is intended for test-catalogue cleanup. It does not delete categories or other catalogue records.

## API operating guide — how the contract works

### Request lifecycle

```mermaid
sequenceDiagram
    participant UI as React UI
    participant Client as frontend/src/services/api.js
    participant Proxy as Nginx / Gunicorn
    participant API as FastAPI router
    participant Guard as Session + role guard
    participant DB as PostgreSQL

    UI->>Client: apiRequest(path, options)
    Client->>Client: Add /api base and bearer token if present
    Client->>Proxy: HTTPS request
    Proxy->>API: Forward to port 8001
    API->>Guard: Validate request and access
    Guard->>DB: Check active staff/customer session when required
    DB-->>Guard: Session and role
    Guard-->>API: Allow or reject
    API->>DB: Execute parameterised query / transaction
    DB-->>API: Result
    API-->>UI: JSON response or HTTP error
```

1. Frontend feature code calls `apiRequest(path, options)`; it does not connect directly to PostgreSQL.
2. `frontend/src/services/api.js` normalises the configured backend URL and ensures the single `/api` prefix is applied once. In development, its fallback is `http://127.0.0.1:8001/api`; production must have the correct `VITE_API_BASE_URL`.
3. The client attaches the staff bearer token from `superbajaar.access_token` unless `skipAuth` is requested. Customer authentication uses a separate customer token flow in the storefront.
4. Nginx proxies the request to the existing FastAPI service on port `8001`.
5. `backend/app/main.py` registers the routers and applies the active-session dependency. CORS origins are controlled by backend settings.
6. `backend/app/core/auth_middleware.py` handles public-route exceptions, validates active staff/customer sessions against PostgreSQL, and applies role restrictions to write requests.
7. Each router validates input, applies its business rules, executes database operations and returns JSON. The browser displays the result; it cannot authoritatively set prices, permissions, stock or order totals.

### Authentication and public-route rules

| Caller / route type | Current rule in backend source |
|---|---|
| Health | `GET /api/health` is public; handler checks database connectivity and returns `200` when connected or `503` degraded when unavailable |
| Staff login | `POST /api/auth/login` is public; returns staff access token on successful authentication |
| Customer registration/login | `POST /api/customer-auth/register` and `POST /api/customer-auth/login` are public; customer sessions are separate from staff sessions |
| Public catalogue | `GET /api/catalogue/categories`, `/products`, `/variants` are public reads |
| Delivery serviceability | `GET /api/delivery/serviceability/{pin_code}` is public |
| Public support / loyalty | Public support ticket submission/tracking and selected loyalty reads/partner enquiry routes have explicit exceptions in middleware |
| Authenticated operations | Other protected requests require a valid bearer token linked to an active, unrevoked, unexpired database session |
| Customer token | Restricted to customer-auth, customer loyalty and website checkout routes; cannot access staff resources |
| Staff token | Role is loaded from the active staff session; write requests are checked against role policy |

### API route inventory — source-level route declarations

All paths below are under the `/api` prefix. This is a source inventory, not a promise that each UI operation or production integration has passed end-to-end testing.

| Domain | Current route groups |
|---|---|
| Health | `GET /health` |
| Staff authentication and users | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `GET/POST /auth/users`, `PATCH /auth/users/{user_id}` |
| Customer authentication | `POST /customer-auth/register`, `POST /customer-auth/login`, `GET /customer-auth/me`, `POST /customer-auth/logout`, `GET /customer-auth/referrals` |
| Catalogue categories | `GET/POST /catalogue/categories`, `PUT /catalogue/categories/{category_id}` |
| Catalogue products | `GET/POST /catalogue/products`, `PUT /catalogue/products/{product_id}`, `POST /catalogue/products/{product_id}/archive` |
| Multi-category products | Product create/update accepts `category_ids`; product reads return assigned category IDs. `category_id` remains the legacy/default category. A product appears in each assigned category without duplicating the product record. |
| Catalogue availability | `GET /catalogue/stock-locations`, `GET/PUT /catalogue/products/{product_id}/availability-rules` |
| Attributes | `GET /catalogue/attributes`, `POST /catalogue/attributes`, `PUT /catalogue/attributes/{attribute_id}/options`, `GET /catalogue/products/{product_id}/attributes`, `PUT /catalogue/products/{product_id}/attributes/{attribute_id}` |
| Variants and prices | `GET/POST /catalogue/products/{product_id}/variants`, `PUT /catalogue/variants/{variant_id}`, `POST /catalogue/variants/{variant_id}/archive`, `GET /catalogue/variants`, `PUT /catalogue/variants/{variant_id}/price` |
| Product images | `GET/POST /catalogue/products/{product_id}/images`, `PUT /catalogue/products/{product_id}/images/{image_id}/primary`, `POST /catalogue/products/{product_id}/images/upload` |
| Inventory | `GET/POST /inventory/locations`, `GET /inventory/balances`, `GET /inventory/movements`, `POST /inventory/adjustments`, `POST /inventory/issues`, `POST /inventory/transfers`, `POST /inventory/counts` |
| Orders | `GET/POST /orders`, `GET /orders/summary`, `GET /orders/{order_id}`, `PATCH /orders/{order_id}/status`, `GET /orders/{order_id}/history` |
| Payments | `GET /payments/reconciliation`, `PATCH /payments/{payment_id}/status` |
| Delivery | `GET /delivery/serviceability/{pin_code}`, `GET/POST /delivery/shipments`, `PATCH /delivery/shipments/{shipment_id}/status`, `GET /delivery/shipments/{shipment_id}/history` |
| Customers and support | `GET/POST /customers`, `PATCH /customers/{customer_id}`, `GET/POST /customers/support-cases`, `PATCH /customers/support-cases/{case_id}`, `POST /customers/support-portal/tickets`, `GET /customers/support-portal/tickets/{case_number}` |
| Purchasing | `GET/POST /purchasing/suppliers`, `GET /purchasing/orders`, `GET/POST /purchasing/orders`, `GET /purchasing/orders/{purchase_id}`, `POST /purchasing/orders/{purchase_id}/receive`, `POST /purchasing/orders/{purchase_id}/cancel`, `POST /purchasing/orders/{purchase_id}/approve` |
| Loyalty | `GET /loyalty/rules`, `GET /loyalty/admin/rules`, `GET /loyalty/customer/account`, `GET /loyalty/customer/me`, `GET /loyalty/quote`, `PUT /loyalty/rules`, `POST /loyalty/admin/earn`, `POST /loyalty/admin/redeem`, `GET /loyalty/admin/accounts`, `GET /loyalty/admin/accounts/{account_id}/transactions`, `POST /loyalty/partner-enquiries`, `GET /loyalty/admin/partner-enquiries` |

### Common HTTP outcomes and debugging sequence

| HTTP status | Meaning for this application | First place to inspect |
|---|---|---|
| `200/201` | Request completed / resource created | Response body and resulting record |
| `401` | Missing, invalid, expired or revoked session | Token source, login response, session row and Authorization header |
| `403` | Caller is authenticated but role/token type cannot perform the action | Middleware role policy and caller type |
| `404` | Route or requested resource not found | Browser Network URL, deployed FastAPI route and resource identifier |
| `409` | Conflict such as duplicate or invalid state transition | Database constraint and domain rule |
| `422` | Request validation or referenced input is invalid | Exact request payload and Pydantic/schema validation |
| `503` | Database/configuration/dependency unavailable | Backend logs, safe configuration presence, DB connectivity and migration compatibility |

**Debug in this order:** browser Network request → exact method/path/body/response → FastAPI route declaration and OpenAPI schema → authentication/role guard → SQL/schema dependency → backend runtime logs. Use Swagger/OpenAPI to inspect and test the contract before changing application code. Use AWS checks only when evidence points to deployed runtime, environment, logs, networking or infrastructure.

> [!CAUTION]
> Never “fix” a 404/401/403/422/503 by changing the public API prefix, opening permissions broadly, changing ports, bypassing authentication, creating a replacement database or editing an already-applied migration. Identify the failing layer first.

### API integration limitations to keep visible

- Payment module source explicitly describes payment records; it does not initiate external gateway charges. Gateway confirmation/refunds are not integrated.
- Delivery module source says carrier integrations are not enabled. Shipment status records are not live carrier tracking.
- Order placement does not currently prove stock has been reserved/deducted.
- Health is a liveness/database connectivity check, not a complete readiness test for every dependency or workflow.
- A route can exist while a corresponding frontend screen, role path, external integration or complete workflow remains incomplete.

## Database and schema

- PostgreSQL is the production database; do not switch to SQLite.
- `backend/schema/`: versioned SQL schema changes used by the current project workflow.
- `database/`: existing database-related assets; inspect their actual usage before changing them.
- Use parameterised queries and transactions where required.
- Schema changes must be reviewed, idempotent where appropriate, and applied through the existing safe migration workflow.
- Never run destructive reset, drop, or truncate operations against production.
- Do not put database credentials or other secrets in source control.

### Schema file inventory and protected files (observed on main)

**Do not edit, delete, rename, replace, or regenerate these protected files:**

- `backend/schema/000_baseline_schema.sql` — protected baseline schema; never modify or delete.
- `backend/schema/009_loyalty_programme.sql` — protected applied migration; never modify or delete.

Treat these as explicit handbook rules, not suggestions. Any future schema change must be added as a new migration file; do not amend an existing/applied migration. Check the full directory and migration history before selecting the next unused migration number. The current repository already contains `010_customer_accounts_referrals.sql` and `011_customer_phone_uniqueness.sql`; do not assume `010` is available.
- `backend/schema/009_product_availability_delivery.sql` — product POS/website availability, delivery options and availability-rule table.
- `backend/schema/010_customer_accounts_referrals.sql` — customer accounts/referrals changes.
- `backend/schema/011_customer_phone_uniqueness.sql` — customer phone uniqueness change.

**Important: two migration files currently use the `009` prefix:** `009_loyalty_programme.sql` (protected) and `009_product_availability_delivery.sql` (added by PR #138). Do not rename, delete, reorder, or edit either file as a quick fix. Before applying any migration in a live environment, inspect the schema runner's ordering and the production `schema_migrations` records to confirm both files are handled safely. Do not apply or reapply the product availability migration until its live application status and ordering are confirmed.

### Data and table preservation — mandatory

- Treat **every existing production table and all its data as protected**. The examples below are not an exhaustive table inventory.
- Never drop, truncate, recreate, rename, or clear an existing table as part of feature work or a schema reset.
- Core business tables that must be preserved include products, categories, product attributes, product variants, product images, customers, orders, payments, inventory/stock locations and balances, purchasing/suppliers, deliveries/shipments, users, user sessions, and loyalty data wherever those tables exist in the active schema.
- The availability migration adds columns to `public.products` and creates `public.product_availability_rules`; it must not replace or recreate `products`.
- Before any schema change, compare the migration against existing schema files and the actual database. Use additive, idempotent migrations where appropriate; take a verified backup and use the approved schema runner.
- Do not assume this README is a live inventory of production tables. Confirm actual table names and migration history against the target database before making changes.

## Business modules to preserve

Storefront, product catalogue, categories, attributes, variants, pricing/GST, customers, authentication/permissions, inventory/warehouses, purchasing/vendors, orders, payments/refunds, delivery, POS, accounting/tax, loyalty, HR/payroll, and reporting.

A module is not considered functional merely because its page or route exists. Verify the UI → API request → backend behaviour → PostgreSQL operation → response flow.

## Deployment and verification rules

- Keep the existing AWS Amplify, EC2, Nginx and PostgreSQL setup.
- Keep backend port `8001` and PostgreSQL port `5432`.
- Keep `/api` as the single public API prefix. Do not introduce API version segments.
- Test on a branch created from `main`; do not push directly to `main`.
- Before changing an endpoint, check both its frontend caller and backend route, including request/response field names and authentication requirements.
- Before changing schema, check existing schema files and production compatibility.
- Report only checks actually run and distinguish local tests from live AWS verification.

## Database safety and release process

Super Bajaar uses a repository-based database migration runner, automated checks, and GitHub branch protection to reduce the risk of accidental schema changes and unverified releases.

### What is in place

- **Safe migration runner:** `backend/scripts/apply_schema.sh` supports dry-run and status modes, checks the migration ledger and file checksums, takes and validates a backup before applying changes, and runs each migration in its own transaction.
- **Failure handling:** failed or changed migrations are reported and recorded. The runner uses exit codes to distinguish safe completion, non-required failures, missing required schema, backup failures, and setup/concurrency problems.
- **Baseline protection:** an unrecorded `000_baseline_schema.sql` is refused when the database already contains user objects. The baseline is intended only for a genuinely empty-database bootstrap.
- **Least-privilege database access:** the runner does not grant blanket permissions across all tables or sequences. A migration must declare only the specific permissions required for the objects it creates.
- **Legacy migration filename protection:** automated validation preserves the four existing legacy files using the `009` and `012` prefixes and rejects additional reuse of those numbers.
- **Automated PostgreSQL compatibility checks:** the GitHub Actions workflow `.github/workflows/migration-check.yml` tests the schema and migration runner on disposable PostgreSQL 15 and 16 databases. It applies the schema files twice and runs the runner test suite.
- **Protected main branch:** the active GitHub ruleset `Protect main` requires pull requests, successful `database-files (15)` and `database-files (16)` checks, and an up-to-date branch. It also blocks force pushes and deletion of the default branch.

### Required workflow for future changes

1. Create a feature branch from the latest `main`; do not push directly to `main`.
2. Read `docs/DATABASE_CHANGE_RULES.md` before any database, schema, migration, data, backup, or deployment work.
3. Keep existing/applied schema files unchanged. Use the approved additive migration process for necessary schema changes, and update `backend/schema_required.txt` when application code requires a new schema file.
4. Open a pull request with the project template. Review the complete diff and wait for required checks to pass.
5. Keep the PR branch up to date with `main`. Merge only through the protected pull-request workflow.
6. Before a production deployment or migration, complete the read-only checks in `docs/RELEASE_GATES.md`, inspect the live migration ledger/checksums, and confirm backup readiness. Production migration/deployment is a separate owner-approved action.

### What these checks do not prove

Successful CI checks prove the tested code and schema passed on disposable PostgreSQL 15 and 16 environments. They do **not** connect to or validate the production database, inspect its live migration ledger or data, create a production backup, prove every application workflow works, or authorize a production deployment. Those checks remain separate release responsibilities.

### Detailed documentation

- [Database change rules](docs/DATABASE_CHANGE_RULES.md)
- [Database release gates and production preflight](docs/RELEASE_GATES.md)
- [Pull request checklist](.github/pull_request_template.md)
- [Migration check workflow](.github/workflows/migration-check.yml)
- [AI coding-agent instructions](AGENTS.md) and [Claude instructions](CLAUDE.md)


## System architecture and end-to-end workflows

This section describes the architecture visible in the repository and the intended business journeys. A diagram is a guide to the flow; it does not certify that every screen, API operation, integration, or production deployment is complete.

### 1. Application and infrastructure architecture

```mermaid
flowchart TB
    subgraph Client["Customer and team devices"]
        C["Customer browser / mobile browser"]
        A["Admin and employee browser"]
    end

    subgraph Frontend["Frontend — AWS Amplify"]
        SF["React + Vite storefront"]
        AC["React admin console / workspaces"]
        API["Shared API client<br/>frontend/src/services/api.js"]
    end

    subgraph Backend["Backend — AWS EC2"]
        N["HTTPS / Nginx reverse proxy"]
        G["Gunicorn process"]
        F["FastAPI application<br/>backend/app/main.py"]
        M["CORS + active-session authentication"]
        R["API routers<br/>catalogue · inventory · orders · payments<br/>delivery · customers · purchasing · loyalty · auth"]
    end

    subgraph Data["Persistent data"]
        PG[("PostgreSQL<br/>sb_app · port 5432")]
        LEDGER["schema_migrations ledger"]
    end

    C --> SF
    A --> AC
    SF --> API
    AC --> API
    API -->|"HTTPS /api/*"| N
    N -->|"127.0.0.1:8001"| G
    G --> F
    F --> M
    M --> R
    R --> PG
    PG --- LEDGER
```

**Request path**

1. The browser loads the React application from AWS Amplify.
2. Storefront or admin components call the shared API client in `frontend/src/services/api.js`.
3. The API client builds the configured backend URL, adds the `/api` prefix and attaches the relevant bearer token when available.
4. HTTPS traffic reaches the existing Nginx reverse proxy on the EC2 host.
5. Nginx forwards backend traffic to the existing Gunicorn/FastAPI service on `127.0.0.1:8001`.
6. FastAPI applies middleware, active-session checks and route-level validation/permissions.
7. The route performs the business operation and reads/writes PostgreSQL on port `5432`.
8. FastAPI returns a response; the frontend renders the result or an error.

**Important boundaries**

- AWS Amplify serves the frontend; it is not the authoritative business-logic or database layer.
- FastAPI is the single authoritative API/backend.
- PostgreSQL is the persistent source of truth. Browser storage may hold temporary UI state such as a cart or token; it is not authoritative for prices, tax, stock, permissions or order totals.
- The existing systemd service/timer and deployment synchronisation are operational/deployment mechanisms, not part of each customer's HTTP request path.
- Keep the existing AWS, Nginx, Gunicorn, port and database arrangement unchanged unless an approved and verified change requires otherwise.

### 2. Customer workflow — website storefront

```mermaid
flowchart TD
    S["Open Super Bajaar storefront"] --> B["Browse categories / search products"]
    B --> P["Open product, select variant and quantity"]
    P --> W["Optional: wishlist / customer sign-in"]
    P --> C["Add item to cart"]
    W --> C
    C --> PIN["Enter or confirm delivery PIN"]
    PIN --> CHECK["Proceed to website checkout"]
    CHECK --> SERVER["Backend validates request and calculates price from active variant"]
    SERVER --> ORDER["Create website order"]
    ORDER --> STATUS["Order appears in operational order workflow"]
    STATUS --> PAY["Payment record / payment status workflow"]
    PAY --> DELIVERY["Shipment and delivery status workflow"]
    DELIVERY --> END["Customer checks order / delivery updates"]
```

**Customer journey details**

1. Customer opens the public storefront and loads active catalogue categories, products and variants.
2. Customer browses/searches, opens a product, selects an available variant and quantity, then adds it to the cart. Wishlist and recently viewed items are storefront conveniences.
3. Customer can sign in/register where the customer-account flow is available and provide delivery/contact details.
4. Customer checks delivery serviceability using the PIN-code flow shown in the storefront.
5. Website checkout submits an order request. The backend must validate the request and calculate authoritative prices from active variants; never trust browser-submitted totals.
6. The order is created with the website channel and enters the operational order process.
7. Payment and delivery records/statuses are handled through their respective workflows.

**Current limitations — do not imply these are already solved**

- Website checkout is documented for `channel=website`; the backend calculates prices from active variants.
- Stock reservation/deduction is proposed in draft PR #158 and is not merged or production-active. That branch now fails closed when a website/manual order lacks a delivery PIN and rejects caller-selected locations for those channels; POS must provide a staff-selected stock location. Do not treat reservation as active until the PR blockers are resolved, PostgreSQL-backed transaction tests pass, and the owner approves merge/release.
- Payment gateway confirmation and refunds are not integrated. New payment records remain pending; captured/refunded states must not be manually asserted.
- Delivery updates depend on the available shipment/status operations; do not promise live carrier tracking unless an integration is implemented and verified.
- API liveness does not guarantee database readiness or successful end-to-end checkout.

### 3. Admin workflow — owner and administrator

```mermaid
flowchart TD
    LOGIN["Admin opens /admin"] --> AUTH["Sign in"]
    AUTH --> ROLE{"Role is owner or admin?"}
    ROLE -->|No| DENY["Admin Console access denied by current frontend gate"]
    ROLE -->|Yes| DASH["Dashboard / module launcher"]
    DASH --> CAT["Catalogue: categories, products, attributes, variants, images"]
    DASH --> PRICE["Pricing and promotions workspace"]
    DASH --> BUY["Purchasing: suppliers, purchase orders, receive goods"]
    DASH --> INV["Inventory: locations, balances, movements, adjustments"]
    DASH --> ORD["Orders: review, process, update status"]
    DASH --> PAY["Payments: review records and permitted status operations"]
    DASH --> DEL["Delivery: shipments and status updates"]
    DASH --> CUST["Customers, support cases and loyalty"]
    DASH --> OTHER["POS, accounting, HR, reports and settings"]
    CAT --> DB[("FastAPI APIs + PostgreSQL")]
    PRICE --> DB
    BUY --> DB
    INV --> DB
    ORD --> DB
    PAY --> DB
    DEL --> DB
    CUST --> DB
    OTHER --> DB
```

**Admin operating sequence**

1. Owner/admin signs in and passes the current frontend role gate.
2. Dashboard provides entry points to separate business workspaces.
3. Admin maintains catalogue data: categories, products, attributes, variants and product images.
4. Admin configures pricing/promotions where the relevant functionality is implemented.
5. Purchasing users maintain suppliers and purchase orders, then record receipt through the available receiving operation.
6. Inventory users review locations, balances and movements; adjustments must follow the permission and audit rules.
7. Order operators review orders and use allowed status transitions.
8. Payment and delivery operators manage the records and status operations actually supported by the APIs.
9. Customer/support and loyalty work is handled in their respective modules.
10. Reports, accounting, POS, HR/payroll and settings are separate workspaces; a visible workspace is not proof that its complete business process is implemented.

**Admin safety rules**

- Use the relevant workspace and API; do not bypass backend permissions by relying on frontend visibility.
- Backend-calculated values and database records are authoritative.
- Financial/payment status, stock adjustments, user roles and destructive data operations require the appropriate permission and audit trail.
- Do not treat a purchase order as received stock until a valid receiving/GRN operation has completed.

### 4. Employee workflow — manager, staff and viewer

The API role policy is documented in `docs/api-contracts.md`. Employee permissions are role-limited; an employee must not receive owner/admin access merely to complete routine work.

```mermaid
flowchart TD
    E["Employee signs in"] --> R{"Assigned role"}
    R --> M["Manager"]
    R --> S["Staff"]
    R --> V["Viewer"]
    M --> MT["Operational work within manager permissions"]
    S --> ST["Limited order, delivery and support-case tasks"]
    V --> VT["Read-only access"]
    MT --> API["FastAPI validates active session and permission"]
    ST --> API
    VT --> API
    API --> DB[("PostgreSQL")]
    API --> RESULT["Return permitted result or reject operation"]
```

**Role boundaries**

| Role | Intended workflow / access |
|---|---|
| Owner / Admin | Full administration. Only owners may grant owner/admin roles, as defined by the API role policy. |
| Manager | Operational writes in inventory, orders, payments, delivery, customers and purchasing. No user administration or catalogue/settings writes. |
| Staff | Limited order, delivery and support-case operations. Cannot change prices, make inventory adjustments, alter payment states or administer users. |
| Viewer | Read-only access to permitted information. |

**Important current UI limitation:** `frontend/src/app/router.jsx` currently allows entry to the Admin Console only for `owner` and `admin`. The API role policy describes manager, staff and viewer permissions, but the current frontend does not yet provide those roles the same Admin Console entry. Do not assume the employee workspace experience is complete until role-specific UI navigation and end-to-end permissions are implemented and tested.

### 5. Business workflow boundaries and implementation status

The repository contains separate workspaces for Commerce, Operations and other business functions. Their presence in the navigation is not proof that all steps in a full ERP lifecycle are implemented.

| Business area | Current documented/API-backed scope | Do not assume |
|---|---|---|
| Catalogue | Categories, products, attributes, variants and images routes | Every catalogue UI action is complete without end-to-end verification |
| Inventory | Locations, balances, movements and adjustments | Automatic reservation/deduction during checkout |
| Purchasing | Suppliers, purchase orders and receiving operation | A complete RFQ → quotation comparison → approval → PO → GRN → vendor bill → payment chain |
| Orders | Create/list/read/summary and status update routes | Every fulfilment automation or stock allocation exists |
| Payments | Payment records and status operation | Live gateway capture, settlement or refund integration |
| Delivery | Shipment records and status updates | Carrier integration or live tracking |
| Customers/support | Customer records and support-case operations | Every CRM automation |
| Loyalty | Loyalty routes and storefront integration points | All reward accounting/redemption scenarios without tests |
| POS, accounting, HR/payroll, reports, settings | Separate frontend workspaces are present | Complete operational APIs and end-to-end workflows unless verified |

When a workflow is implemented or materially changed, update this table and the relevant diagram in the same pull request. Mark a feature complete only after checking the UI → API → backend permission/business rule → PostgreSQL → response path.

