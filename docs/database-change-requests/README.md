# Database Change Request Register

All requests below are design-only until the Database Owner reviews and approves the logical schema, exact migration number, grants and disposable database test plan. No request in this register authorises production migration.

| Request | Scope | Main owner decisions |
|---|---|---|
| `enterprise-approval-audit-scope.md` | Shared organisation, department/store/facility scopes, maker-checker and audit | Canonical org tree, role/scope separation, immutable audit contract |
| `purchasing-landed-cost-allocation.md` | Supplier invoice freight/discount allocation into stock/COGS | Allocation basis, tax treatment, cost adjustment subledger and accounting entries |
| `pricing-price-books-promotions.md` | Price books, promotions, eligibility, stacking, history and resolver | Store/channel scope, discount policy, price approval and order snapshots |
| `multi-store-pos-registers-tenders.md` | Store registers, cashier shifts, cash drawer, split tender and receipt sequence | Register concurrency, cash evidence, receipt series and tender policy |
| `payment-refund-settlement-controls.md` | Partial/full refunds, provider settlement, fees and bank reconciliation | Provider contracts, refund approvals, settlement matching and Finance mappings |
| `order-tax-snapshots-and-accounting-event-posting.md` | Immutable GST/order snapshots and configurable sales/payment/COGS posting | GST/CA policy, source-event outbox, mapping roles and immutability |
| `delivery-proof-carrier-events.md` | Carrier webhooks, POD, RTO and reverse shipment | POD evidence, privacy/retention, carrier contract and reverse logistics |

## Migration governance gate

The latest source ZIP contains schema files through `035_inventory_facility_internal_locations.sql`, while some governance documents still describe an older sequence. The Database Owner must reconcile the actual production `schema_migrations` ledger/checksums and update the stale sequence documentation before assigning any new migration number. Never infer production migration state from the ZIP.
