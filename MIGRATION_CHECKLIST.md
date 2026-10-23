# Odoo → Super Bajaar migration checklist

## Discovery (before export)
- [ ] Confirm Odoo version, hosting and database backup/restore process.
- [ ] List installed modules, custom modules, website(s), companies and currencies.
- [ ] Identify product templates, variants, attributes, categories, images, barcodes and units.
- [ ] Identify warehouses, stock locations, stock moves, lots/expiry, reservations and inventory valuation method.
- [ ] Identify suppliers, purchase orders, receipts and supplier bills.
- [ ] Identify customers, addresses, sales orders, invoices, returns, refunds and POS orders.
- [ ] Identify pricelists, discounts, taxes, fiscal positions, payment/shipping providers and website rules.
- [ ] Identify user roles, custom fields, automated actions and external integrations.

## Data preparation
- [ ] Take a verified backup and test restore.
- [ ] Export source IDs and record source row counts/totals.
- [ ] Map every source field to a destination field or document why it is excluded.
- [ ] Resolve duplicate SKUs/barcodes and orphaned variant/category references.
- [ ] Validate units, currency, tax mapping, prices and image URLs/files.
- [ ] Separate current stock balances from historical stock movement records.
- [ ] Decide treatment of open orders, open purchase orders, unpaid invoices and pending returns.
- [ ] Do not import passwords or payment secrets as plain text.

## Dry run and cutover
- [ ] Run import in staging with row-level error output.
- [ ] Reconcile counts by entity and totals by currency/tax/period.
- [ ] Validate sample products end-to-end: search → variant → PIN code → cart → order simulation.
- [ ] Validate inventory by warehouse and variant; reconcile opening stock with approved source totals.
- [ ] Validate access roles and PII visibility.
- [ ] Get business owner sign-off and agree a maintenance/cutover window.
- [ ] Freeze or incrementally sync source changes during final cutover.
- [ ] Keep a rollback path and preserve the source Odoo backup.
