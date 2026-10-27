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

Set `SB_DATABASE_PATH` to a persistent writable path and `SB_CORS_ORIGINS` to the exact deployed storefront origin. Before real traffic, connect the existing React UI, test end-to-end, review security, and use managed persistent storage for multi-instance deployment. Do not commit `.env` or production secrets.
