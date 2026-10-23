# Super Bajaar — API and module plan

## Initial release scope
1. Public storefront and product discovery.
2. Product master, variant/SKU data model.
3. Admin authentication and catalogue management.
4. Backend API and serviceability contract.
5. Migration preview/import foundation.

## Product master field groups
### Product (parent)
- `id` (internal stable ID)
- `external_source`, `external_id` (migration/source traceability)
- `name`, `slug`, `description`, `brand_id`
- `category_id`, `product_type`, `status`
- `country_of_origin`, `manufacturer`, `packaging_information`
- `created_at`, `updated_at`, `created_by`, `updated_by`

### Product variant / sellable SKU
- `id`, `product_id`, `external_source`, `external_id`
- `sku` (required, unique in defined scope), `barcode` (optional, unique when supplied)
- `variant_name`, `attribute_values` (e.g. size, colour, pack size)
- `unit_of_measure`, `net_quantity`, `net_quantity_unit`
- `image_url` or managed image references
- `mrp`, `selling_price`, `currency`, `price_list_id`
- `tax_category_id`, `hsn_code` (where applicable)
- `track_inventory`, `allow_backorder`, `status`

### Related entities (not fields crammed into product)
- Variant price events: variant, seller/channel, price, effective timestamp, source and actor.
- Warehouse stock: variant, warehouse, on-hand, reserved, available, safety stock.
- Stock movements: receipt, sale, return, transfer, adjustment, opening balance; reference and audit actor.
- Seller listing: seller, variant, seller SKU, price, status and service areas.
- Serviceability: PIN code, region, warehouse/seller coverage and delivery rules.
- Supplier/product link: supplier SKU, purchase UOM, lead time and minimum order quantity.

## Later modules
- Inventory: warehouses, stock locations, movements, reservations, batches/expiry/serials when needed.
- Purchase: suppliers, RFQ, purchase orders, receipts, supplier bills and landed costs.
- Sales: website orders, POS/live sales, invoices, fulfilment, returns, refunds and credit notes.
- Accounting: chart of accounts, journals, receivables/payables, bank reconciliation, GST and period closing.
- Seller operations: onboarding/KYC, listings, commission rules, settlements and seller reports.
- Migration: import jobs, mapping profiles, dry-run preview, row-level validation errors, idempotency, audit log and reconciliation.

## API design rules
- Use stable internal IDs; keep Odoo IDs as external references.
- Use pagination, filters and explicit API versioning.
- Use decimal types for money, never floating-point arithmetic for authoritative totals.
- Make import and order endpoints idempotent where appropriate.
- Record actor, timestamp and source for important changes.
- Restrict customer PII by role and audit access.
- Enforce region/stock/price/tax rules server-side.
