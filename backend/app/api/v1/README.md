# Versioned API routes

- `health.py`: process health check; no database access.
- `catalogue.py`: initial category and product CRUD endpoints backed by PostgreSQL. Requires `DATABASE_URL` and the target schema. Does not run migrations automatically.

Catalogue endpoints:

- `GET /api/v1/catalogue/categories`
- `POST /api/v1/catalogue/categories`
- `GET /api/v1/catalogue/products`
- `POST /api/v1/catalogue/products`

These are the first catalogue API foundations, not a complete product-variant or inventory workflow. Use a dedicated test database before enabling in deployment.
