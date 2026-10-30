# Application Audit Register

**Purpose:** Track the full application audit before the consolidated repair/release phase. For every module, record (A) issues fixable with the current application/database contract and (B) requirements that genuinely need a database/schema change.

**Operating rule:** Trace the existing UI -> frontend service/API -> backend route/service -> existing schema contract before proposing anything new. Reuse existing tables, columns, APIs and workflows where possible. Do not create duplicate structures.

## Working method

1. Audit one module and follow its links into dependent modules.
2. Reproduce/trace each error and identify its actual cause.
3. Record schema-independent fixes separately from schema requirements.
4. Implement and test safe schema-independent fixes as we go, on feature branches.
5. Add schema-dependent requirements here with affected code paths, rationale, dependencies and acceptance criteria. Do not write or apply SQL as part of this audit.
6. After the module audit is complete, review and consolidate the schema register, resolve overlaps, then prepare the owner-approved migration plan.
7. No production DB changes, merge or deployment without the Repository Owner's explicit approval.

## Status definitions

- **Confirmed:** traced to code/schema evidence or reproducible test.
- **Candidate:** suspected; needs tracing or reproduction.
- **Blocked on owner/schema:** cannot safely complete until Database Owner supplies/approves the schema change or live-state check.
- **In progress:** implementation underway.
- **Verified:** relevant tests/build/runtime check actually passed. State exactly which check; do not infer live verification from CI.

---

# Module audit

## 1. Catalog

**Status:** Not yet audited in this register. This is the first module to trace.

### Schema-independent fixes
| ID | Issue / affected path | Evidence | Planned fix | Verification | Status |
|---|---|---|---|---|---|
| CAT-NOSCHEMA-001 | Pending full Catalog UI -> API -> backend -> schema trace | Not yet traced | Inspect existing implementation first; fix broken wiring, validation, rendering and queries that use existing schema | Targeted backend tests + frontend builds; runtime only if available | Candidate |

### Schema requirements
| ID | Requirement | Why existing schema is insufficient | Affected code | Dependencies / acceptance criteria | Status |
|---|---|---|---|---|---|
| CAT-SCHEMA-001 | None confirmed yet | Catalog audit not complete | TBD | Do not add a requirement until traced | Candidate |

## 2. Inventory and order fulfilment

**Status:** Initial code/schema investigation recorded; full screen-by-screen audit remains open.

### Existing structures to reuse
- `stock_locations` (warehouse/store/dark_store, PIN and active state)
- `inventory_balances` (on-hand and reserved quantities per variant/location)
- `inventory_movements` (receipt, sale, return, adjustment, transfer, reservation and release movements)
- `purchase_orders` and `purchase_order_lines` (ordered/received quantities)
- `orders` and `order_lines`
- `payments`
- `deliveries` (includes `location_id`)
- `order_status_history` and `delivery_status_history`
- Existing inventory count/adjustment APIs and basic goods-receipt endpoint

These are repository findings, not confirmation of the live production schema. Verify live ledger/schema with the Database Owner before release.

### Schema-independent work already prepared
| ID | Work | Location | Verification / status |
|---|---|---|---|
| INV-NOSCHEMA-001 | Atomic order stock reservation using existing balances and movement references; release on cancellation; consume on dispatch; prevent over-dispatch/repeated deduction; support partial dispatch | PR #158 | Draft PR; backend tests and frontend builds reported green in PR checks; not merged/deployed |
| INV-NOSCHEMA-002 | Show order lines and remaining quantities; allow partial dispatch quantities in delivery workspace | PR #159 | Draft PR; both frontend builds reported green; depends on PR #158; not merged/deployed |

### Schema requirements identified so far
| ID | Requirement | Why needed | Acceptance criteria | Status |
|---|---|---|---|---|
| INV-SCHEMA-001 | Inventory batch/lot tracking, including batch number and expiry metadata | Existing aggregate balance does not represent individual lots/expiry | Receive and track lots independently; trace lot balances and movements | Candidate; owner review required |
| INV-SCHEMA-002 | First-class goods-receipt (GRN) header and line records | Existing basic receive-goods flow updates PO received quantities and stock but does not provide a complete GRN record/workflow | Record GRN identity, PO/vendor, received lines/quantities, timestamps and audit linkage | Candidate; owner review required |
| INV-SCHEMA-003 | Batch-level reservation allocation and batch linkage on stock movements where required | Aggregate reservation does not identify the lot selected for fulfilment | Allocate reservations to lots; support traceability and FEFO dispatch; preserve existing aggregate ledger semantics | Candidate; owner review required |
| INV-SCHEMA-004 | Return inspection/quarantine records and line-level disposition | Existing return movement alone does not represent inspection, quarantine and restock/reject outcomes | Returned goods can be inspected, quarantined, restocked or rejected with auditable quantities and reason | Candidate; owner review required |

**Related inventory request:** PR #157 (documentation-only inventory-to-order schema change request). Reconcile that request with this register before any future migration proposal. Do not assume PR #157 is approved or applied.

**Open technical checks:** Verify delivery/order line SQL against the exact schema columns; inspect order/delivery status transition synchronization; verify live schema and migration ledger with owner. Payment-failure stock release remains unimplemented until a trusted, verified provider failure event/status is available.

## 3. Purchasing / Procurement

**Status:** Not yet audited. Trace request -> approval -> vendor quotation -> PO -> dispatch -> GRN -> quality check -> vendor invoice/bill -> approval -> payment.

### Schema-independent fixes
| ID | Issue / affected path | Evidence | Planned fix | Verification | Status |
|---|---|---|---|---|---|
| PUR-NOSCHEMA-001 | Pending full module trace | Not yet traced | Reuse existing purchasing APIs and PO structures; fix safe UI/API/validation gaps | Targeted tests/builds | Candidate |

### Schema requirements
| ID | Requirement | Why needed | Affected code | Acceptance criteria | Status |
|---|---|---|---|---|---|
| PUR-SCHEMA-001 | To be determined after trace | Do not assume GRN, invoice or approval schema is absent until existing tables and links are inspected | TBD | Record only confirmed gaps; reconcile shared GRN requirements with Inventory | Candidate |

## 4. Accounting

**Status:** Not yet audited. Trace accounts, journals, ledger, invoices, bills, payments, tax/GST and reconciliation screens and their links to Purchasing, Orders and Payments.

### Schema-independent fixes
| ID | Issue / affected path | Evidence | Planned fix | Verification | Status |
|---|---|---|---|---|---|
| ACC-NOSCHEMA-001 | Pending full module trace | Not yet traced | Reuse existing accounting structures and fix code/UI/API issues that do not require schema changes | Targeted tests/builds | Candidate |

### Schema requirements
| ID | Requirement | Why needed | Affected code | Acceptance criteria | Status |
|---|---|---|---|---|---|
| ACC-SCHEMA-001 | To be determined after trace | No schema gap is asserted before inspecting current schema and references | TBD | Include only evidence-backed requirements; coordinate shared payment/vendor/customer entities | Candidate |

## 5. Remaining modules

Audit each module and its cross-module links. Add separate schema-independent and schema-dependent rows for each:
- Sales / Orders / Checkout
- Customers / CRM
- Payments / Gateway callbacks / Refunds
- Delivery / Logistics
- POS
- Loyalty
- Website / Storefront
- HR / Payroll
- Reports / Dashboard / Settings / Administration
- Imports / Exports / Bulk operations

No module is considered audited merely because its landing page loads. Follow important actions through to backend and data persistence.

---

# Cross-module issue log

| ID | Modules affected | Issue | Root cause / evidence | Fix path | Status |
|---|---|---|---|---|---|
| XMOD-001 | TBD | Record shared entity/API/schema mismatches discovered while tracing module links | TBD | Resolve once at shared layer; avoid module-specific duplicates | Candidate |

# Consolidated schema backlog

This section is the eventual owner-review queue. Add an item only after checking existing schema files and application references. For every item record:
- business capability and user-visible failure;
- exact tables/columns/constraints/indexes proposed (as a requirement, not SQL);
- existing structures checked and why they cannot satisfy the need;
- code paths that will consume the change;
- compatibility and existing-data considerations;
- live checks the Database Owner must perform;
- acceptance tests and whether deployment is blocked.

Do not put credentials, secrets, customer data or production dumps in this file.

# Final audit exit criteria

- Every module and important cross-module workflow has been traced from UI to persistence.
- Every observed error has a reproducible case or clearly labelled unresolved evidence.
- Schema-independent issues are fixed and tested where safe; remaining ones have explicit blockers.
- Schema-dependent requirements are deduplicated and reviewed as one coherent backlog.
- Existing structures are reused; no duplicate table/API/workflow is introduced without evidence.
- No production schema/data changes occur during the audit.
- The Repository Owner approves the final migration plan separately.
