# Super Bajaar

Super Bajaar is a commerce storefront and ERP application. This file is the single project guide: it explains the current structure, what each important file does, how requests flow, and how the application is deployed.

## Fixed technology and runtime

- Frontend: React + Vite, hosted on AWS Amplify.
- Backend: FastAPI on AWS EC2, behind the existing Nginx configuration.
- Database: PostgreSQL.
- Backend port: `8001` (keep unchanged).
- PostgreSQL port: `5432` (keep unchanged).
- Frontend development port: `5173` (existing Vite configuration).
- API prefix: `/api/v1` (the prefix configured by the backend).
- Do not add ports, services, databases, or deployment targets without an identified need and approval.
- Never reset or clear production data as part of routine development.

## Main request flow

1. A page or form in the frontend calls the shared frontend API client.
2. The API client sends an HTTP request to the backend URL with the required authentication token.
3. A route in `backend/app/api/v1/` receives and validates the request.
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
- `backend/app/api/v1/auth.py`: authentication endpoints.
- `backend/app/api/v1/catalogue.py`: catalogue, categories, product attributes and variants endpoints.
- `backend/app/api/v1/inventory.py`: inventory endpoints.
- `backend/app/api/v1/purchasing.py`: purchasing endpoints.
- `backend/app/api/v1/orders.py`: order endpoints.
- `backend/app/api/v1/payments.py`: payment endpoints.
- `backend/app/api/v1/delivery.py`: delivery endpoints.
- `backend/app/api/v1/customers.py`: customer endpoints.
- `backend/app/api/v1/health.py`: health endpoint.
- `backend/tests/`: backend tests.

The route files on the current codebase include some direct database access. A separate service/repository layer is not assumed to exist everywhere. Extract code only when a verified fix or maintenance need justifies it; do not rewrite working modules just to match a folder pattern.

## Database and schema

- PostgreSQL is the production database; do not switch to SQLite.
- `backend/schema/`: versioned SQL schema changes used by the current project workflow.
- `database/`: existing database-related assets; inspect their actual usage before changing them.
- Use parameterised queries and transactions where required.
- Schema changes must be reviewed, idempotent where appropriate, and applied through the existing safe migration workflow.
- Never run destructive reset, drop, or truncate operations against production.
- Do not put database credentials or other secrets in source control.

## Business modules to preserve

Storefront, product catalogue, categories, attributes, variants, pricing/GST, customers, authentication/permissions, inventory/warehouses, purchasing/vendors, orders, payments/refunds, delivery, POS, accounting/tax, loyalty, HR/payroll, and reporting.

A module is not considered functional merely because its page or route exists. Verify the UI → API request → backend behaviour → PostgreSQL operation → response flow.

## Deployment and verification rules

- Keep the existing AWS Amplify, EC2, Nginx and PostgreSQL setup.
- Keep backend port `8001` and PostgreSQL port `5432`.
- Keep the configured API prefix `/api/v1`; align frontend callers with real backend routes rather than introducing another prefix.
- Test on a branch created from `main`; do not push directly to `main`.
- Before changing an endpoint, check both its frontend caller and backend route, including request/response field names and authentication requirements.
- Before changing schema, check existing schema files and production compatibility.
- Report only checks actually run and distinguish local tests from live AWS verification.
