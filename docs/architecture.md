# Super Bajaar Architecture

## Initial delivery
The customer storefront is the first delivery. It must read catalogue, prices and serviceability from a backend API. Do not hardcode products, stock, customers, order counts, sellers or prices in frontend source.

## Target modules
- Storefront and customer accounts
- Product master, categories, attributes, variants, SKU and barcode
- Pricing and auditable price history
- Warehouses, inventory ledger, batches and opening balances
- Suppliers, supplier-product terms and purchasing
- Sales orders, POS/live sales, returns and refunds
- Accounting, GST configuration, receivables/payables and reconciliation
- Sellers, fulfilment, delivery, admin, reports and migration manager

## Boundaries
The browser must never hold database credentials, Odoo administrator credentials, or payment secrets. Validate access and business rules on the server. Use role-based permissions and audit logs for admin actions. Payment integration is deliberately deferred.

## Odoo migration
Inspect the existing Odoo version, installed modules, custom fields and source IDs first. Map entities and relationships, run a dry run, report errors/duplicates, reconcile record counts and financial/stock totals, then perform an approved import with backups and a rollback plan. Do not assume Odoo remains the live source of truth after cutover until the migration strategy is explicitly selected.
