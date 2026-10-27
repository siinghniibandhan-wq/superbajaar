# Super Bajaar

A fresh React/Vite storefront backed by a Python API and the existing application database.

## Catalogue behaviour
- The website reads the current product catalogue from `GET /api/products`.
- No sample products, product backups, CSV imports, or background synchronisation are included.
- Product visibility depends on the records and active statuses in the connected database.
- Database credentials stay on the backend.

## Frontend
Run `npm install`, then `npm run dev`. Run `npm run build` to create the production bundle.

Set `VITE_API_BASE_URL` only when the API is hosted on a different origin. If frontend and API share a domain, leave it unset.

## Backend
Install `backend/requirements.txt`, set `DATABASE_URL` to the existing PostgreSQL database, and run `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000`.

This app reads the existing database; it does not create a product copy or run continuous synchronisation. Schema changes must be reviewed separately and must not be applied blindly to production.

## Database schema migrations

Schema updates are applied automatically by the production deploy runner. No manual SQL is needed.

**Rules for schema files**
- Files live in backend/schema and are named NNN_name.sql (three digits, lowercase letters, digits and underscores).
- Write them idempotently (IF NOT EXISTS, guarded ALTER statements). Never DROP or TRUNCATE existing data.
- Never edit a file after it has been applied. A changed checksum fails the deploy. Add a new numbered file instead.

**How it works**
- The runner /home/ec2-user/deploy/deploy.sh (triggered by sb-deploy.timer every 2 minutes) deploys new commits from main only.
- Before the symlink swap and restart, it calls /home/ec2-user/deploy/bin/apply_schema.sh, a server copy of backend/scripts/apply_schema.sh.
- The script takes a verified pg_dump backup (in /home/ec2-user/schema-backups), applies only unrecorded files (one transaction each), records them in the schema_migrations table with a sha256 checksum, grants the app database role access, and smoke-tests /api/products.
- If a migration fails, the commit is marked failed and the previous release keeps running. Restore from the backup manually if ever needed.
- Logs: /home/ec2-user/deploy/schema.log.

**Rebuilding the server**
1. Copy backend/scripts/apply_schema.sh to /home/ec2-user/deploy/bin/apply_schema.sh (owner ec2-user, mode 755).
2. In deploy.sh, add this line just above the line "mv $T $D":
   [ -d $T/backend/schema ] && { /home/ec2-user/deploy/bin/apply_schema.sh $T/backend/schema || fail "schema migration (see /home/ec2-user/deploy/schema.log)"; }
3. Ensure ec2-user can run "sudo -n -u postgres" without a password.
4. Do a dry run first: bash apply_schema.sh <schema_dir> --dry-run

Product data is never migrated by this process.

## How the ERP is connected

Every module reads and writes the same records, so a step in one place moves the next module's worklist.

**Purchase → Inventory → Accounting** (admin: Purchase, Inventory, Accounting)
1. *Requisitions & Orders*: create a PR → approve → record the vendor quotation (or compare several) → convert to a PO.
2. Record the vendor dispatch, then create the **GRN** into a warehouse and bin.
3. **Quality check** on the GRN: accepted units are added to the stock ledger in their bin; rejected units create a **vendor return** and a **debit note** automatically.
4. Enter the vendor invoice as a **bill** → approve (three-way match against accepted goods) → pay. Debit notes are deducted from the bill.

**Website order → Logistics → Accounting** (admin: Sales, Logistics)
`placed` (stock reserved) → `confirmed` → `processing` → `packed` (stock leaves, shipment created) → `shipped` → `out_for_delivery` → `delivered` (sale, GST and cost of goods booked; invoice becomes a receivable). Logistics can advance the shipment instead; the order follows. Cancelling releases stock. Sales returns raise credit notes.

**Accounting** shows receivables and payables with ageing, invoice and bill status, credit/debit note register, and a check of documents against the ledger.

**Single sources of truth**: stock = `sb_inventory_ledger` (+ `sb_stock_reservations`); journal = `sb_journals` / `sb_journal_lines`. Never write to the legacy stock or journal tables. `backend/tests/test_erp_wiring.py` guards this.

**Code map**: `backend/app/erp_core.py` (stock + journal helpers), `order_flow.py` (website order lifecycle), `integrated_operations.py` (purchase documents, QC, bills, invoices, returns), `erp_flow.py` (`/api/erp/*` screens API), `src/erp.jsx` (admin screens). Migration `015_erp_unification.sql` is applied by the normal deploy.

## Admin screens for the connected flow (`src/erp.jsx`)

Every screen below calls the workflow API (`/api/erp/*` plus the `/admin/*` document routes), so one action updates stock, accounting and the next team's worklist.

| Module | Tab | What it does |
|---|---|---|
| Purchase | Requisitions & Orders | PR → approve → vendor quotation (or compare several) → PO → vendor dispatch → GRN into a bin → quality check → vendor bill → approval → payment. The card always shows the next action. |
| Purchase | Vendors | Register, edit, activate/deactivate vendors (terms, GSTIN, payable, unapplied debit notes). |
| Purchase | Returns & Debit Notes | Rejected goods become a vendor return plus a debit note, which reduces the vendor bill automatically. |
| Purchase | Bills & Payments | Approve, reject and pay vendor bills. |
| Sales | Sale (website orders) | placed → confirmed → processing → packed → shipped → out for delivery → delivered, showing stock reservation, shipment and invoice per order. |
| Sales | Customers | Customer master with credit days, GSTIN, invoiced and outstanding totals. |
| Logistics | Shipments / Tracking | Shipments appear when an order is packed. Moving them forward moves the order, and delivery books the sale. |
| Accounting | Receivables & Payables | Aging, overdue, top customers/vendors, invoice and bill status, ledger reconciliation. |
| Accounting | Credit & Debit Notes | One register: credit notes (sales returns) and debit notes (purchase returns). |

Deploying: migration `015_erp_unification.sql` must be applied (`backend/scripts/apply_schema.sh backend/schema`) before these screens work. The API role cannot create tables itself.
