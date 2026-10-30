# Database Change Request — Inventory to Order Fulfilment

**Status:** Proposed for Database Owner review  
**Scope:** Add only missing capabilities. Reuse existing inventory, purchasing, order, payment and delivery tables.  
**Safety:** This is a requirements document, not SQL. No schema file, migration, database, data or production service has been changed.

## 1. Existing objects to extend/reuse

The current repository schema already provides:

- `stock_locations`: warehouses, stores and dark stores, including PIN and active state.
- `inventory_balances`: aggregate `on_hand` and `reserved` quantities by variant and location.
- `inventory_movements`: receipt, sale, return, adjustment, transfer, reservation and release movement types.
- `purchase_orders` and `purchase_order_lines`: ordered and received quantities.
- `orders` and `order_lines`: order header and variant quantities.
- `payments`: payment lifecycle records.
- `deliveries`: shipment records with an existing `location_id`.
- `order_status_history` and `delivery_status_history`: existing status audit trails.

Do not create duplicate balance, movement, purchase-order, order, payment, location or delivery tables.

## 2. Confirmed repository gaps

The checked-in schema and repository search did not reveal:

- Batch/lot-level stock with expiry and remaining quantity.
- A first-class GRN header and receipt-line record (the current receive endpoint directly updates PO received quantity, aggregate balance and movement).
- An order-linked reservation ledger and batch allocation records.
- A durable return/quarantine inspection workflow.
- A persisted fulfilment location on the order itself.

The existing `reserved` balance and reservation/release movement types are useful primitives, but do not identify which order owns a reservation or which batch is allocated.

## 3. Minimal additive schema proposal

### A. `inventory_batches` — new

Track one received stock lot per variant/location/receipt line:

- identity primary key
- `variant_id` → `product_variants.id`
- `location_id` → `stock_locations.id`
- `purchase_order_line_id` → `purchase_order_lines.id`
- `goods_receipt_line_id` → new GRN line
- `batch_number`
- `received_date`
- nullable `expiry_date`
- `quantity_received`, `quantity_remaining`
- `status` (available, quarantine, blocked, expired)
- created/updated timestamps

A batch is not sellable when expired, quarantined, blocked, or depleted. Existing aggregate stock is not silently converted into invented batches; it remains legacy/unbatched stock until the owner approves a separately controlled opening-stock process.

### B. `goods_receipts` and `goods_receipt_lines` — new

Create a durable GRN record linked to the existing purchase order:

- Header: unique GRN number, purchase order, received date (defaults to current date in application), note, created-by and created-at.
- Lines: purchase-order line, variant, received quantity, batch number, optional expiry date, and the resulting batch reference.

One PO line may be received across multiple batches and multiple GRNs, while the existing PO received quantity remains the authoritative cumulative received quantity. Enforce that cumulative receipt never exceeds the outstanding PO quantity inside one transaction.

### C. `inventory_reservations` and `inventory_reservation_allocations` — new

Reservation header/line ledger must link reservation to an order, variant, location, quantity, status, expiry and lifecycle timestamps. Allocation rows link each reservation to one or more batches and quantities.

- Reservation creation and updates to existing `inventory_balances.reserved` plus `inventory_movements` must be atomic.
- Use row locks to prevent overselling.
- A reservation must be idempotent per order/variant.
- Unpaid reservation expiry is 30 minutes; payment confirmation keeps it active.
- Cancellation or verified payment failure releases it exactly once.
- Existing orders are not silently reserved retroactively.

### D. Extend existing tables (no replacements)

- Add nullable `orders.fulfilment_location_id` referencing `stock_locations.id`, so the chosen source location is persisted on the order.
- Add nullable `inventory_movements.batch_id` referencing `inventory_batches.id`, preserving all existing aggregate movement rows.
- Continue using `inventory_balances` as the aggregate balance/projection and `inventory_movements` as the common audit ledger.

### E. `inventory_returns` and `inventory_return_lines` — new

Record return against the existing order/delivery, variant, quantity, received location, reason and inspection outcome. Returned stock initially enters quarantine and is unavailable for sale. Only an explicit accepted inspection may move accepted quantity back to sellable batch stock. Rejected/damaged quantity remains blocked or is written off through the existing inventory movement audit.

## 4. Required business invariants

1. FEFO allocation: eligible, non-expired batches with the earliest expiry first; FIFO by received date when expiry is absent. Never allocate expired, quarantined or blocked stock.
2. Reserve all order lines atomically or reserve none.
3. A location must be eligible for the delivery PIN and have sufficient available stock for the complete order. Persist that location on the order.
4. Website/manual allocation follows the approved PIN/location selection rule; POS uses the staff-selected location and validates it.
5. Dispatch consumes only the quantity actually dispatched; partial dispatch is supported and consumes only its corresponding batch allocations.
6. Cancellation and verified payment failure release outstanding reservations once. Do not infer gateway success/failure without verified provider status.
7. Return stock remains quarantined until inspection and explicit acceptance.
8. Every receipt, reservation, release, dispatch, return, inspection and adjustment is traceable through the existing movement ledger and linked records.
9. All writes that affect PO received quantities, batches, balances, reservations, order state or movements are transactionally consistent.
10. Preserve all existing data and aggregate stock. No destructive conversion/backfill is included in this request.

## 5. Application files expected to consume these objects

- `backend/app/api/purchasing.py`: GRN creation and multi-batch receiving.
- `backend/app/api/inventory.py`: batch listing, expiry visibility and controlled batch adjustments.
- `backend/app/api/orders.py`: location selection, atomic reservation, cancellation release and order fulfilment location.
- `backend/app/api/payments.py`: release on verified failed/cancelled payment only.
- `backend/app/api/delivery.py`: batch-aware partial dispatch, stock deduction and return intake/inspection.
- Corresponding backend tests and existing purchasing, inventory, order and delivery workspaces.

The application must detect missing optional schema and return a clear feature-level unavailable response; it must not take down unrelated pages or endpoints.

## 6. Owner checks required before implementation can depend on the new objects

- Confirm the live `schema_migrations` ledger and actual production definitions for the listed existing tables/columns.
- Confirm the next unused migration filename using both the schema directory and live ledger. Do not infer a migration number from the repository alone.
- Review this proposal, adjust names/constraints/permissions as the Database Owner, and author/apply the migration under the repository's database governance process.
- Test migration twice on disposable PostgreSQL 15 and 16 and include least-privilege grants for the application role.
- Add the approved migration to `backend/schema_required.txt` in the same change that first requires it.
- Do not deploy or enable code requiring the new schema until the owner confirms it is applied and the release gates are satisfied.

## 7. Explicit exclusions

No SQL has been authored or run by this change. No live database was queried. No migration was applied. No production data was changed. No merge or deployment is authorised by this request.
