# API contracts

All new endpoints should be versioned under `/api/v1`, return validated response schemas, enforce authentication/permissions, and document error responses.

Initial endpoint domains:
- health and readiness
- authentication, users and access control
- categories, products, attributes and variants
- inventory and pricing
- serviceability, cart and checkout
- orders, payments and refunds
- delivery and admin operations

Contracts must be written before wiring each frontend feature. Payment webhooks must verify provider signatures and be idempotent.
