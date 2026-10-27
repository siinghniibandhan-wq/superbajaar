# Database assets

SQL files in this directory are reference/migration assets only. Nothing in this folder runs automatically.

Before applying a schema change:
1. Confirm the target database and environment.
2. Take a suitable backup.
3. Review the migration for destructive statements.
4. Apply through an explicit migration procedure.
5. Verify schema and application health afterwards.

Do not put credentials in SQL files. This scaffold has not connected to or modified any database.


## Current modular API migration order

The following files are explicit reference migrations and are **not automatically applied**:

1. `schema.sql` — catalogue, variants, locations and inventory base tables.
2. `migrations/002_orders.sql` — orders and order lines.
3. `migrations/003_payments.sql` — payment records (not gateway integration).
4. `migrations/004_delivery.sql` — delivery records (not carrier integration).
5. `migrations/005_customers_support.sql` — customer directory and support cases.
6. `migrations/006_purchasing.sql` — suppliers, purchase orders and order lines.
7. `migrations/007_access_control.sql` — user accounts and revocable sessions.
8. Any optional feature-specific migrations only after review.

Apply the base schema before migrations that reference its tables. Review the actual database first: `CREATE TABLE IF NOT EXISTS` does not repair a pre-existing table with a different structure. Back up the intended database and verify all foreign keys before applying.

## Current implementation limitations

- The purchasing API can record suppliers, orders and goods receipts; supplier invoices, payments and quotation comparison are not implemented.
- Payment rows are not a gateway integration. Do not treat a client-supplied reference as proof of capture.
- Authentication endpoints and session schema exist, but **the full API is not yet protected by authentication/role enforcement**. Do not expose this backend publicly as production-ready until route protection, login UI, rate limiting and authorization checks are completed.
- No migration in this list has been applied or verified against the live database by this code work.
