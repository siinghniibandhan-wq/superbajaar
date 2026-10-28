# API contracts

All API routes use the single `/api` prefix. Authenticated requests require a bearer token backed by an active, non-revoked database session.

## Public storefront
- `GET /api/health` — API liveness only; it does not guarantee database availability.
- `POST /api/auth/login`
- `GET /api/catalogue/categories` — active categories only.
- `GET /api/catalogue/products` — active products only for public requests.
- `GET /api/catalogue/variants` — active variants belonging to active products.
- `POST /api/orders` — public checkout accepts only `channel=website`; the server calculates prices from active variants.

## Authentication and user administration
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET/POST /api/auth/users`
- `PATCH /api/auth/users/{user_id}`

## Catalogue
- `GET/POST /api/catalogue/categories`
- `GET/POST /api/catalogue/products`
- `GET/POST /api/catalogue/attributes`
- `GET /api/catalogue/products/{product_id}/attributes`
- `PUT /api/catalogue/products/{product_id}/attributes/{attribute_id}`
- `GET/POST /api/catalogue/products/{product_id}/variants`
- `GET/POST /api/catalogue/products/{product_id}/images`
- `GET /api/catalogue/variants`
- `PUT /api/catalogue/variants/{variant_id}/price`

## Operations
- Inventory: `GET/POST /api/inventory/locations`, `GET /api/inventory/balances`, `GET /api/inventory/movements`, `POST /api/inventory/adjustments`
- Orders: `GET/POST /api/orders`, `GET /api/orders/summary`, `GET /api/orders/{order_id}`, `PATCH /api/orders/{order_id}/status`
- Payments: `GET/POST /api/payments`, `PATCH /api/payments/{payment_id}/status`
- Delivery: `GET/POST /api/delivery/shipments`, `PATCH /api/delivery/shipments/{shipment_id}/status`
- Customers/support: `GET/POST /api/customers`, `PATCH /api/customers/{customer_id}`, `GET/POST /api/customers/support-cases`, `PATCH /api/customers/support-cases/{case_id}`
- Purchasing: `GET/POST /api/purchasing/suppliers`, `GET/POST /api/purchasing/orders`, `GET /api/purchasing/orders/{purchase_id}`, `POST /api/purchasing/orders/{purchase_id}/receive`

## Role policy
- Owner/admin: full access; only owners may grant owner/admin roles.
- Manager: operational writes in inventory, orders, payments, delivery, customers and purchasing; no user administration or catalogue/settings writes.
- Staff: limited order, delivery and support-case operations; cannot modify prices, inventory adjustments, payment states or users.
- Viewer: read-only access.
- Public callers: catalogue reads and website checkout only.

## Known limitations
- Stock reservation/deduction during order placement is not implemented. Order creation must not be treated as proof that stock has been reserved.
- Payment gateway confirmation/refunds are not integrated. New payment records remain pending; captured/refunded states cannot be manually asserted.
- Public checkout needs edge-level rate limiting/bot protection before high-volume production use.
- API liveness is not a database readiness check.
