# Super Bajaar — Storefront

Responsive React + Vite storefront using the original Super Bajaar purple-and-orange brand.

## Run locally

```bash
npm install
npm run dev
```

Create a production bundle with:

```bash
npm run build
npm run preview
```

## Storefront features

- Home page, department browsing, search, sorting, and offer filtering
- Product detail pages with selectable variants and SKU identifiers
- Branded fallback artwork when an external product image cannot load
- Wishlist, shopping bag, quantity controls, and order summary
- SB Plus membership preview with working navigation
- Help centre with locally saved demo support requests and browser-local order lookup
- `WELCOME10` demo coupon (10% off, capped at ₹300)
- Product image fallback artwork and asynchronous image decoding
- Delivery PIN entry and address form validation
- Local demo order history and responsive mobile layout

## Integrated storefront and API

The React storefront now calls the FastAPI service for the live catalogue, customer registration/sign-in, authenticated cash-on-delivery checkout, order-history refresh, and support requests. If the API cannot be reached, the storefront keeps its sample catalogue available for browsing; when the API responds successfully with an empty catalogue, it shows no products rather than pretending the samples are live inventory.

Set `VITE_API_BASE_URL` in the frontend build environment to the deployed backend origin. Both an origin such as `https://api.example.com` and an origin ending in `/api` are accepted. The API uses `SB_CORS_ORIGINS`, `SB_SECRET_KEY`, `SB_ADMIN_EMAIL`, `SB_ADMIN_PASSWORD`, and a persistent `SB_DATABASE_PATH`; see `backend/README.md`.

## Remaining before live launch

- Admin product/order management UI and full operational workflows
- Production build and end-to-end tests against the deployed API
- Verify persistent database storage, backup/restore, and production security controls
- Confirm live catalogue data, stock, tax, PIN-code serviceability, delivery rules, and published policies
- Razorpay integration and payment verification (intentionally deferred to the final stage)

COD orders are submitted to the server for signed-in customers; the server recalculates the order total and checks available stock. Online payment remains disabled. Never place secret payment credentials in frontend code.

## Stack

- React 18
- Vite 6
- lucide-react
