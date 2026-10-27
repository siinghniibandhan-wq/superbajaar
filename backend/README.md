# Super Bajaar API

FastAPI service for product catalogue, stock, customer accounts, server-priced orders, order status and support requests. PostgreSQL is the application's database; the service creates its required tables and index at startup with idempotent `CREATE TABLE IF NOT EXISTS` statements.

## Local setup

1. Create a PostgreSQL database and a database user with permission to connect and create tables/indexes.
2. Set `DATABASE_URL` to the PostgreSQL connection URL, for example `postgresql://USER:PASSWORD@HOST:5432/superbajaar`. URL-encode special characters in the username or password.
3. Set a random `SB_SECRET_KEY` of at least 32 characters and a strong `SB_ADMIN_PASSWORD`. Configure `SB_ADMIN_EMAIL` before the first API startup to provision the admin if that email does not already exist.
4. Install dependencies and start the API:

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env
# Export the variables from .env using your preferred environment loader.
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

- Health: `GET /api/health`
- Interactive schema: `/docs`
- Products: `GET /api/products`
- Registration/login: `POST /api/auth/register`, `POST /api/auth/login`
- Checkout locks inventory rows in a transaction to prevent concurrent overselling.
- Price history records initial prices and later price changes only; the API never invents historic prices.
- Online payment is not implemented yet.

The storefront uses customer registration/login, live catalogue retrieval, authenticated COD checkout, order history and support requests. When `SB_ADMIN_EMAIL` and `SB_ADMIN_PASSWORD` are configured, startup ensures that email has the admin role and resets its password hash to the configured password. Keep these values restricted to trusted deployment secrets; changing them changes the configured admin account on the next startup. Do not commit `.env` or production secrets.

## Smoke test

With the API running and `SB_ADMIN_EMAIL` / `SB_ADMIN_PASSWORD` configured, run `python tests/smoke_test.py` from `backend`. The script creates a test customer, product and order; use a non-production database.


## Delivery PIN coverage

Set `SB_SERVICEABLE_PINS` to a comma-separated allowlist of six-digit PIN codes served by the store, for example `110001,110085,560001`. `GET /api/delivery/availability?pin=110085` returns `serviceable` or `not_serviceable`. If the variable is empty, the API returns `not_configured` and order creation is blocked with HTTP 503. Configure at least one six-digit PIN before accepting orders or running the order smoke test. This is a store-configured allowlist, not a courier-provider lookup or delivery-time estimate.

Order creation returns the final server-priced order items as well as the total, so the storefront receipt uses the prices actually recorded by the backend.
