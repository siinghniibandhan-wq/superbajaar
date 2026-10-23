# Super Bajaar API

## Local development
1. Create a Python 3.12 virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Configure `DATABASE_URL` and `CORS_ALLOWED_ORIGINS` in your local environment (never commit credentials).
4. Apply the reviewed SQL files to a development PostgreSQL database in numeric order.
5. Start the API from the repository root with `uvicorn backend.app.main:app --reload --port 8000` or from this directory with `uvicorn app.main:app --reload --port 8000`.

## Initial routes
- `GET /health` — process health, no database required.
- `GET /ready` — database readiness check.
- `GET /api/products` — published, active catalogue with current price and available quantity.
- `GET /api/serviceability?pincode=110001` — checks configured active warehouse coverage and available inventory.

The API deliberately does not seed sample products. Catalogue queries return only published active products from the database. Serviceability remains unavailable until operations has loaded and verified the real coverage records.

## Current limitations
Authentication, admin authorization, product writes, customer/order/cart APIs, image upload, rate limiting and payment are not implemented. Do not expose privileged endpoints or launch this API to production until these are implemented and tested.
