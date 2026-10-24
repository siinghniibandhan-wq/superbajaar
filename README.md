# Super Bajaar — Website-First Commerce Platform Starter (v0.3)

**Brand:** Super Bajaar  
**Tagline:** Your Everyday Super Store

This package starts with the customer-facing website, while establishing the product/SKU and migration foundations needed for Inventory, Purchase, Sales/POS, Accounting, Sellers, Delivery and Admin modules later.

## Included
- React + Vite storefront with soft, light and dark themes.
- API-driven catalogue: no fabricated product, stock, customer, order, sales, seller or price-history records.
- PIN-code serviceability flow, variant selection, cart API call, seller application flow and API-backed admin workspace.
- Product and variant field dictionary.
- Empty CSV migration templates for products, variants, categories, inventory, suppliers, customers and historical orders.
- Starter SQL schema for product templates, variants, warehouses and stock balances.
- Odoo migration plan, field mapping and validation checklist.

## Run the website
1. Install Node.js 20+.
2. Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to the backend API.
3. Run `npm install`.
4. Run `npm run dev`.
5. Run `npm run build` to verify the production frontend build.

The frontend is a scaffold and will show a clear API connection state until a backend is connected. It is not a live commerce system yet.


## Architecture
`Customer Website / Admin UI → Backend API (authentication + business rules) → Odoo and/or application database`

Odoo is the existing system to inspect first. Before creating a parallel source of truth, decide which data Odoo will continue to own and which services need to be rebuilt. Product, variant, customer, order, inventory and accounting records should not be independently duplicated without a defined synchronisation and reconciliation policy.

## Product and SKU principles
- A **product** is the parent catalogue record.
- A **variant** is a distinct sellable configuration and normally has its own SKU, barcode, price and stock tracking.
- SKU must be unique within the agreed business scope. Do not use a display name as a SKU.
- Keep external Odoo IDs for traceability during migration.
- Stock is a ledger of movements/balances by variant and warehouse, not one global hardcoded number.
- Regional availability is calculated server-side using PIN code, variant, seller/warehouse, stock and fulfilment rules.
- Price history is append-only and must be imported from real records. Never invent a historical low price.

## Migration templates
CSV files under `migration-templates/` are **header-only templates**, not populated example data. Map source Odoo exports to them after inspecting the real Odoo modules and custom fields. Use UTF-8 CSV and preserve source IDs in `external_source` / `external_id` fields.

Suggested migration sequence:
1. Inspect Odoo version, installed apps, custom modules, websites, companies, warehouses, pricelists, taxes and access rules.
2. Export and back up source data; record row counts and totals.
3. Map categories and attributes, then products and variants.
4. Validate SKU uniqueness, barcode uniqueness, units, taxes, images and price lists.
5. Import warehouses and opening stock with a dated, approved opening-balance process.
6. Import suppliers and customers with privacy controls.
7. Import historical orders and price events only where records are available and relationships can be preserved.
8. Reconcile counts, inventory valuation/quantities, order totals, tax totals and customer references.
9. Run a test migration in staging, obtain sign-off, then schedule a production cutover and rollback plan.

## API contract currently expected by the frontend
- `GET /products?search=&category=&pincode=&sort=` → `{ "items": [] }` or an array.
- `GET /serviceability?pincode=110085` → `{ "serviceable": true, "message": "", "region_id": "", "delivery_estimate": "" }`.
- `POST /cart/items` → server-validated cart response. Recheck current price, stock and serviceability.
- `POST /seller-applications` → pending-review application.
- `GET /admin/dashboard` → authenticated, role-filtered metrics and lists.

Production also needs authenticated product/variant CRUD, image upload, stock movement, supplier and purchase order APIs, sales/POS, orders/returns, customer data, audit log, import jobs, import preview/errors, reconciliation, role-based access and monitoring. See `docs/API_AND_MODULE_PLAN.md`.

## Security and compliance notes
- Never expose Odoo credentials, database passwords or privileged tokens in browser code or `VITE_*` variables.
- Admin screens must be protected by backend authentication and role-based permissions; hiding a button is not access control.
- Backend must validate prices, taxes, inventory, seller status, PIN-code eligibility and cart/order totals.
- Payment integration is intentionally postponed. When added, order creation, signature verification, webhooks, refunds and reconciliation must be server-side.
- Treat legal, GST, Legal Metrology, FSSAI/BIS and marketplace obligations as review items for qualified Indian legal/accounting professionals before launch.

## Current limitations
This is the website-first starter and migration foundation, not a completed backend, Odoo migration tool, production admin system or payment-ready store. No live data is included. Next implementation step: inspect the actual Odoo setup and implement the backend API and migration dry-run against a backup/staging environment.
