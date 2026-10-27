# API contracts

All new endpoints should be versioned under `/api/v1`, return validated response schemas, enforce authentication/permissions, and document error responses.

## Implemented foundation

- `GET /api/v1/health` — process health check; no database dependency.
- `GET /api/v1/catalogue/categories` — paginated category list.
- `POST /api/v1/catalogue/categories` — create a category; slug conflicts return 409.
- `GET /api/v1/catalogue/products` — paginated product list; optional category and status filters.
- `POST /api/v1/catalogue/products` — create a draft product with optional category and tax metadata.

Catalogue endpoints require `DATABASE_URL` and the target schema to exist. They do not run migrations automatically. Authentication and permission enforcement are not yet implemented, so do not expose write endpoints publicly.

## Planned endpoint domains

- authentication, users and access control
- attributes, valid variants and variant images/SKUs
- inventory and pricing
- serviceability, cart and checkout
- orders, payments and refunds
- delivery and admin operations

Contracts must be written before wiring each frontend feature. Payment webhooks must verify provider signatures and be idempotent.
