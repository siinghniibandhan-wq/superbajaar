# API contracts

All new endpoints are versioned under `/api/v1`. Responses are validated, list endpoints are paginated, and database writes use parameterized SQL.

## Health
- `GET /api/v1/health`

## Categories and products
- `GET /api/v1/catalogue/categories?limit=100&offset=0`
- `POST /api/v1/catalogue/categories`
- `GET /api/v1/catalogue/products?category_id=&status=active&limit=100&offset=0`
- `POST /api/v1/catalogue/products`

## Attributes and variants
- `GET /api/v1/catalogue/attributes`
- `POST /api/v1/catalogue/attributes`
- `GET /api/v1/catalogue/products/{product_id}/attributes`
- `PUT /api/v1/catalogue/products/{product_id}/attributes/{attribute_id}`
- `GET /api/v1/catalogue/products/{product_id}/variants`
- `POST /api/v1/catalogue/products/{product_id}/variants`

Attribute definitions support text, number, boolean, date, select, multi-select, colour and size values. Variant creation accepts only active attributes marked as variant attributes, validates required attributes and allowed options, enforces non-negative prices and unique SKUs through database constraints.

## Important limitations
These endpoints require `DATABASE_URL` and the reviewed target schema. They do not migrate the database. Authentication, roles, image upload/storage, variant-combination uniqueness, stock transactions and end-to-end integration tests are still pending. Do not expose write endpoints publicly until authentication and permissions are implemented.
