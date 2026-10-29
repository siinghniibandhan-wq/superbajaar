# Super Bajaar

Super Bajaar is a commerce storefront and ERP application. This file is the single project guide: it explains the current structure, what each important file does, how requests flow, and how the application is deployed.

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
- Catalogue: `GET/POST /catalogue/categories`, `GET/POST /catalogue/products`, `GET /catalogue/attributes`, `POST /catalogue/attributes`, `GET /catalogue/products/{product_id}/attributes`, `PUT /catalogue/products/{product_id}/attributes/{attribute_id}`, `GET/POST /catalogue/products/{product_id}/variants`, `GET/POST /catalogue/products/{product_id}/images`, `GET /catalogue/variants`, `PUT /catalogue/variants/{variant_id}/price`
- Inventory: `GET/POST /inventory/locations`, `GET /inventory/balances`, `GET /inventory/movements`, `POST /inventory/adjustments`
- Orders: `GET/POST /orders`, `GET /orders/summary`, `GET /orders/{order_id}`, `PATCH /orders/{order_id}/status`
- Payments: `GET/POST /payments`, `PATCH /payments/{payment_id}/status`
- Delivery: `GET/POST /delivery/shipments`, `PATCH /delivery/shipments/{shipment_id}/status`
- Customers and support: `GET/POST /customers`, `PATCH /customers/{customer_id}`, `GET/POST /customers/support-cases`, `PATCH /customers/support-cases/{case_id}`
- Purchasing: `GET/POST /purchasing/suppliers`, `GET/POST /purchasing/orders`, `GET /purchasing/orders/{purchase_id}`, `POST /purchasing/orders/{purchase_id}/receive`

Route existence does not prove that a screen works end to end. For each workspace, check the actual request payload, response fields, authentication and database schema. A missing operation must be implemented against the existing schema and tested; do not invent a second API or change ports to work around it.

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
