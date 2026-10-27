# Super Bajaar API

FastAPI service for product catalogue, stock, customer accounts, server-priced orders, order status and support requests.

## Local setup

```bash
cd backend
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
cp .env.example .env
# Set a random SB_SECRET_KEY of 32+ characters and a strong admin password.
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

- Health: `GET /api/health`
- Interactive schema: `/docs`
- Products: `GET /api/products`
- Registration/login: `POST /api/auth/register`, `POST /api/auth/login`
- Admin catalogue, stock and order status use Bearer-token administrator access.
- Checkout requires a signed-in customer; the server recalculates prices, coupon and delivery, and checks stock.
- 30-day history returns only recorded observations; it does not invent historic prices.
- Online payment is deliberately not implemented yet.

Set `SB_DATABASE_PATH` to a persistent writable path and `SB_CORS_ORIGINS` to the exact deployed storefront origin. The React storefront is connected to customer registration/login, live catalogue retrieval, authenticated COD checkout, customer order history and support requests. An admin console is available to authenticated users whose role is `admin`; configure `SB_ADMIN_EMAIL` and `SB_ADMIN_PASSWORD` before the first API startup to provision that account. If the database already exists, changing these variables does not automatically reset an existing account password or role. Before real traffic, run a production build and end-to-end tests, review security and rate limiting, verify backups and persistent storage, and confirm delivery/tax/legal requirements. SQLite is suitable for a single-instance pilot only; use a managed transactional database before multi-instance or high-volume deployment. Do not commit `.env` or production secrets.
