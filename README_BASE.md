# Super Bajaar — Odoo-first marketplace frontend (v0.2)

This starter intentionally contains **no hardcoded product catalogue, customer records, inventory, order counts, seller records, or price history**. The storefront asks a backend API for products. If the API is unavailable, it shows a connection/empty state rather than fake products or fabricated metrics.

## Design direction
The uploaded Odoo storefront video shows a purple-to-magenta gradient hero, compact category/product browsing, product-detail pages and a dark purple footer. This starter takes inspiration from the colour mood and compact marketplace rhythm, but uses a different layout and components. Three themes are included: `soft` (subtle neumorphic cues), `light`, and `dark`.

## Run
1. Install Node.js 20+.
2. Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to your backend API.
3. `npm install`
4. `npm run dev`
5. `npm run build`

The frontend is an API-ready shell. It is not production-ready until the backend endpoints below are implemented and tested.

## API contract expected by this frontend
- `GET /products?search=&category=&pincode=&sort=` returns `{ "items": [...] }` or a bare array. Each product should include `id`, `name`, `category_name`, `brand`, `description`, `seller_name`, `available`, `stock_status`, and `variants`. Each variant should include `id`, `name`, `sku`, `image_url`, `sale_price`, `mrp`, and `lowest_price_30d`.
- `GET /serviceability?pincode=110085` returns `{ "serviceable": true|false, "message": "...", "region_id": "...", "delivery_estimate": "..." }`. The query string must be `?pincode=`. The backend should validate PIN codes, region mapping, seller coverage, warehouse stock, shipping method and delivery restrictions.
- `POST /cart/items` with `{ "product_id": "...", "variant_id": "...", "quantity": 1, "pincode": "..." }` returns a server-calculated cart. The server must recheck current price, stock, region and seller availability.
- `POST /seller-applications` receives seller onboarding fields. Validate server-side and keep application in a pending-review state until verified.
- `GET /admin/dashboard` returns real metrics only, with sections for products, orders, customers, regions, sellers and settings. Do not expose PII to unauthorised staff.
- Additional production endpoints: authentication/OTP, addresses, wishlist, product/variant admin CRUD, image upload, stock by warehouse and region, seller KYC, orders, returns/refunds, grievance tickets, price-event audit, tax/invoice and shipping.

## Odoo integration approach
Odoo remains the system of record for products, variants, categories, images, price lists, stock, customers, sales orders and potentially inventory locations. Use a **server-side integration/BFF** between this React storefront and Odoo:
- Never expose Odoo API keys, database credentials or admin tokens in the browser.
- Map Odoo product templates and variants to a stable storefront API contract.
- Use Odoo pricelists and company/website rules as appropriate.
- Calculate availability by PIN code using explicit service areas, seller serviceability, warehouse stock, delivery rules and variant-specific inventory. A PIN code alone is not proof that an item can be delivered.
- Use server-side caching carefully and invalidate on stock/price updates.
- Preserve Odoo as source of truth; do not fork duplicate product/customer databases without a clear sync strategy.

## Region and PIN-code model
A practical data model needs `service_region`, `serviceable_pincode`, `seller_service_area`, `warehouse`, `warehouse_stock`, `delivery_rule` and the mapping from product/variant to eligible seller/warehouse. A product should be purchasable only if the chosen variant is active, stock is available, a seller is active, the PIN code maps to an active service region and a fulfilment route is available. The backend must enforce this at search, product detail, cart and order creation—not only hide it in the UI.

## 30-day prior-price display
The UI reads `lowest_price_30d` from the API. It never invents a price. Production should retain append-only price events per variant/SKU, seller, channel and timestamp; calculate the correct 30-day window; define the eligible selling-price basis with legal review; and keep an audit trail. Only show promotional claims when supported by the relevant historical data. Obtain Indian legal advice on the current CCPA/e-commerce requirements and amendments effective from 1 January 2027 before launch.

## Razorpay
Razorpay is intentionally **not activated** in this initial build. Add it after backend order creation, stock reservation, final price/tax calculation, idempotency, webhook signature verification, refunds and reconciliation are implemented. Create orders and verify signatures server-side; never trust a browser success callback as proof of payment.

## Admin workspace
The admin panel is role-protected by design intent, but the starter does not yet implement authentication/permissions. It calls `GET /admin/dashboard` and renders API-returned metrics only. Production roles should include owner/super-admin, catalog manager, operations, customer support, finance, seller manager and read-only auditor. Apply least-privilege access, field-level PII controls and audit logs.

## Production checklist
- Real backend + database; secure auth and role-based access.
- Odoo API credentials in server-side secrets only.
- PIN-code and region eligibility enforced server-side.
- SKU/variant-specific stock, price and image.
- Verified prior-price calculation and immutable audit events.
- Consumer-facing entity, seller, total-price, delivery, cancellation, return/refund, privacy and grievance disclosures.
- Category-specific compliance such as Legal Metrology declarations and FSSAI/BIS requirements where applicable.
- GST/tax/invoice treatment reviewed by Indian CA; marketplace GST/TCS obligations assessed.
- Automated tests, rate limits, logging, monitoring, backups and security review.

This is a frontend scaffold and integration contract, not a claim of legal compliance or a completed live marketplace.
