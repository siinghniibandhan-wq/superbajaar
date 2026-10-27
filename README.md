# Super Bajaar

Responsive React + Vite storefront for Super Bajaar, using the purple-first brand with orange accents. The FastAPI backend uses PostgreSQL for catalogue, inventory, customer accounts, orders, recorded price history, and support tickets.

## Run locally

Frontend:
```bash
npm install
npm run dev
npm run build
```

Backend setup and environment variables are documented in [backend/README.md](backend/README.md). The API requires `DATABASE_URL`, a random `SB_SECRET_KEY` of at least 32 characters, and admin credentials. Configure `SB_CORS_ORIGINS` for the frontend origin and `SB_SERVICEABLE_PINS` with the store's comma-separated six-digit delivery PIN allowlist.

Set `VITE_API_BASE_URL` in the frontend build environment to the backend origin. An origin with or without a trailing `/api` is accepted.

## Current functionality

- Department browsing, catalogue search, sorting, and offer filtering
- Product details, selectable variants, SKU, and recorded 30-day price observations
- Wishlist, shopping bag, quantity controls, and order summary
- Customer registration, sign-in, session validation, and order history
- Server-priced cash-on-delivery checkout with inventory locking and stock validation
- Delivery PIN availability check; checkout is blocked when coverage is missing or the PIN is not serviceable
- Customer cancellation for eligible orders with inventory restoration
- Admin product creation/editing, stock updates, order fulfilment status controls, and support-ticket status management
- Server-side support requests and responsive mobile layout
- Product-image fallback artwork

## Before live launch

- Configure and verify production PostgreSQL, persistent backups, and restore procedures
- Set strong production secrets and restrict CORS to the deployed storefront
- Configure the real delivery PIN allowlist and validate fulfilment operations
- Verify product catalogue, variants, stock, prices, tax treatment, delivery charges, returns/refunds, and published policies
- Run the backend smoke test against a **non-production** database with the API running and the required environment variables set
- Complete Razorpay integration and verify payment webhooks before enabling online payment

Online payment is intentionally disabled; never place secret payment credentials in frontend code. The API records price observations only when a product is created or its selling price changes; it does not fabricate earlier prices.

## Stack

- React 18 and Vite 6
- FastAPI and PostgreSQL
- Python API smoke test: `backend/tests/smoke_test.py`
