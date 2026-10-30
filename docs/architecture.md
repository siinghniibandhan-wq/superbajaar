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


---

## API contracts and access policy

All public API paths use the single `/api` prefix. Authenticated requests require a bearer token backed by an active, non-revoked database session. The route list below is a documented contract; verify it against current backend route declarations before relying on it for implementation or release decisions.

### Public storefront
- `GET /api/health` — health endpoint; consult the current implementation to determine whether it checks only liveness or database readiness.
- `POST /api/auth/login`
- `GET /api/catalogue/categories` — active categories for public requests.
- `GET /api/catalogue/products` — active products for public requests.
- `GET /api/catalogue/variants` — active variants belonging to active products.
- `POST /api/orders` — website checkout; server calculates prices from active variants.

### Authentication and user administration
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET/POST /api/auth/users`
- `PATCH /api/auth/users/{user_id}`

### Catalogue
- `GET/POST /api/catalogue/categories`
- `GET/POST /api/catalogue/products`
- `GET/POST /api/catalogue/attributes`
- `GET /api/catalogue/products/{product_id}/attributes`
- `PUT /api/catalogue/products/{product_id}/attributes/{attribute_id}`
- `GET/POST /api/catalogue/products/{product_id}/variants`
- `GET/POST /api/catalogue/products/{product_id}/images`
- `GET /api/catalogue/variants`
- `PUT /api/catalogue/variants/{variant_id}/price`

### Operations
- Inventory: `GET/POST /api/inventory/locations`, `GET /api/inventory/balances`, `GET /api/inventory/movements`, `POST /api/inventory/adjustments`.
- Orders: `GET/POST /api/orders`, `GET /api/orders/summary`, `GET /api/orders/{order_id}`, `PATCH /api/orders/{order_id}/status`.
- Payments: `GET/POST /api/payments`, `PATCH /api/payments/{payment_id}/status`.
- Delivery: `GET/POST /api/delivery/shipments`, `PATCH /api/delivery/shipments/{shipment_id}/status`.
- Customers/support: `GET/POST /api/customers`, `PATCH /api/customers/{customer_id}`, `GET/POST /api/customers/support-cases`, `PATCH /api/customers/support-cases/{case_id}`.
- Purchasing: `GET/POST /api/purchasing/suppliers`, `GET/POST /api/purchasing/orders`, `GET /api/purchasing/orders/{purchase_id}`, `POST /api/purchasing/orders/{purchase_id}/receive`.

### Role policy
- Owner/admin: full access; only owners may grant owner/admin roles.
- Manager: operational writes in inventory, orders, payments, delivery, customers and purchasing; no user administration or catalogue/settings writes.
- Staff: limited order, delivery and support-case operations; cannot modify prices, inventory adjustments, payment states or users.
- Viewer: read-only access.
- Public callers: permitted public catalogue reads and website checkout only.

### Known limitations to verify before release
- Stock reservation/deduction during order placement may be incomplete; order creation must not be treated as proof that stock has been reserved unless implementation and tests prove it.
- Payment gateway confirmation/refunds may not be integrated. Verify current provider integration and status-transition rules.
- Public checkout requires edge-level rate limiting/bot protection before high-volume production use.
- API liveness does not necessarily prove database readiness.
- Route presence alone does not prove the complete UI → API → permission/business rule → database → response workflow.
