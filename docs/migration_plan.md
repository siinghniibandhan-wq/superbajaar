# Odoo Migration Plan

1. Inventory the source Odoo version, apps, custom fields, integrations and database size.
2. Export metadata and sample records with sensitive fields minimised.
3. Map categories, products, variants/SKUs, suppliers, warehouses, stock, customers, orders and price history.
4. Define stable source-system identifiers and duplicate matching rules.
5. Validate required fields and references; generate a dry-run report before writing data.
6. Import master data first, then suppliers/warehouses, opening stock, and historical transactions in dependency order.
7. Reconcile counts, stock by warehouse/SKU, valuation, order totals, tax totals and account balances.
8. Obtain approval, take backups, execute cutover, monitor errors, and retain rollback capability.

Never commit live customer/supplier data, access tokens, database dumps or credentials to Git. This repository should contain schemas, docs and blank templates only.
