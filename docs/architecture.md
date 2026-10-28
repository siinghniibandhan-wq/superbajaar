# Architecture

## Design goals

1. Build a new modular application rather than extending the legacy single-file implementation.
2. Keep the customer storefront and internal workspaces on a documented API contract.
3. Keep domain logic in services and persistence in repositories; API handlers validate input and enforce access control.
4. Use one canonical record per business entity and explicit transactions for cross-module workflows.
5. Keep the database persistent. App startup must not drop tables, truncate data, or silently reset schemas.

## Target layout

- `frontend/src/app`: app shell, router and providers.
- `frontend/src/pages`: page/workspace entry points.
- `frontend/src/features`: domain-specific UI and client workflows.
- `frontend/src/services`: API client and client service wrappers.
- `backend/app/api`: HTTP route handlers.
- `backend/app/models`: persistence models.
- `backend/app/schemas`: request/response validation.
- `backend/app/services`: domain rules and orchestration.
- `backend/app/repositories`: database access.
- `backend/app/integrations`: external providers only.
- `database`: reviewed SQL assets; never auto-executed at import/startup.

## Domain boundaries

Catalogue/attributes/variants, pricing/promotions, inventory, purchasing, orders, payments/refunds, delivery, customers/CRM/loyalty, POS, accounting/tax, HR/payroll, reporting and access control should have explicit ownership and API contracts. Cross-module operations must use database transactions and idempotency where retries are possible.

## Port compatibility

- Frontend development server: Vite default `5173`.
- Existing backend deployment historically uses `127.0.0.1:8001`.
- PostgreSQL default is commonly `5432`, but the real configured port must be verified from the connection settings.
- The new scaffold does not change production process commands or ports. Confirm service, reverse proxy, health check and frontend API URL before deployment.

## Deployment safety

File moves can break imports, Vite build paths, service startup commands, health checks and deployment roots, but do not inherently change PostgreSQL data. Preserve environment values until the target database is verified. Do not run schema scripts during deployment without an explicit migration step.
