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



# Audit progress dashboard

**Last updated:** 30 October 2026  
**Overall audit:** IN PROGRESS — no business module has a full end-to-end audit sign-off yet.

| Work item | Status | What is actually complete / remaining |
|---|---|---|
| Audit register created in GitHub | <badge>DONE</badge> | Central tracking document committed on this branch |
| Functional capability inventory structure | <badge>DONE</badge> | Capability checklists drafted for all listed modules; implementation verification is still pending |
| Audit classification method | <badge>DONE</badge> | Separate tracking for fixes possible without schema and requirements needing schema |
| Existing-schema-first rule | <badge>DONE</badge> | Reuse existing structures; trace UI -> API -> backend -> schema before proposing additions |
| Inventory initial code/schema reconnaissance | <badge color="warning">PARTIAL</badge> | Existing tables and basic receive/count/adjustment paths identified; full screen-by-screen and live-schema verification remain |
| Inventory schema-gap discovery | <badge color="warning">PARTIAL</badge> | Initial batch/expiry, GRN, batch allocation and returns/quarantine requirements documented; these remain candidates pending full trace and owner review |
| Inventory order reservation / fulfilment code | <badge color="warning">IMPLEMENTED — NOT INTEGRATED</badge> | PR #158 is draft; CI checks were reported green; not merged or deployed |
| Delivery partial-dispatch UI | <badge color="warning">IMPLEMENTED — NOT INTEGRATED</badge> | PR #159 is draft; frontend builds were reported green; depends on PR #158; not merged or deployed |
| Catalog audit | <badge color="secondary">NOT STARTED</badge> | Next module to trace in detail |
| Purchasing audit | <badge color="secondary">NOT STARTED</badge> | Capability checklist exists; no full implementation trace yet |
| Accounting audit | <badge color="secondary">NOT STARTED</badge> | Capability checklist exists; no full implementation trace yet |
| Remaining module audits | <badge color="secondary">NOT STARTED</badge> | Capability checklists exist; implementation traces remain |
| Consolidated migration plan | <badge color="secondary">PENDING</badge> | Prepare only after module audits, deduplication and Database Owner review |
| Production schema changes / deployment | <badge color="secondary">NOT STARTED</badge> | No production DB changes, merges or deployments performed by this audit |

**Status discipline:** DONE means the specific documentation or task is complete. IMPLEMENTED — NOT INTEGRATED means code is in a draft PR but not merged/deployed. PARTIAL means only the stated discovery has been completed. NOT STARTED / PENDING must not be presented as completed work.


# Functional capability inventory

This is a separate deliverable from the defect/schema register. It answers: **What is each module supposed to let a user do?** For every capability, the audit will trace the visible screen/action, frontend handler, API/backend implementation, permissions, and persistence. A capability is not marked available merely because a menu item or button exists.

Capability status:
- **User-confirmed scope:** explicitly described by the Repository Owner.
- **To verify in code:** expected capability area; inspect the actual UI and implementation before claiming it works.
- **Missing / broken:** record the defect in the relevant schema-independent or schema-dependent issue table.
- **Verified working:** only after the end-to-end path is checked.

## Catalog — product and merchandising management

**User-confirmed capabilities**
| Capability group | Functions to inventory | Status |
|---|---|---|
| Product management | Create product; view/list/search products; open product details; edit product; delete/archive product | User-confirmed scope; verify exact actions and implementation |
| Category management | Create category; view/list categories; edit category; delete/archive category | User-confirmed scope; verify exact actions and implementation |
| Subcategory management | Create subcategory; view/list subcategories; edit subcategory; delete/archive subcategory; assign subcategory to parent category | User-confirmed scope; verify exact actions and implementation |
| Attribute management | Manage product attributes; manage attribute values/options; edit and remove attributes/options; assign attributes to products/variants where supported | User-confirmed scope; exact sub-actions and product/variant linkage to verify |

**Additional Catalog areas to inspect, not assumed to exist:** product images/media, SKU/barcode, product type/status, pricing and tax fields, variants, stock/availability display, delivery configuration, SEO/content details, bulk import/export, validation, duplicate handling, and category/attribute dependencies during product edits or deletion.

**Catalog audit output required:** complete screen/action list; API route for each action; tables/columns used; role/permission checks; field validation; empty/error/loading states; tests; and a status for every capability (working, broken, missing, or blocked by schema).

## Inventory — stock control and fulfilment

| Capability group | Functions to inventory | Status |
|---|---|---|
| Stock overview | View stock by product/variant and location; inspect on-hand, reserved and available quantities; low-stock visibility | To verify in code |
| Receipts | Receive purchased goods; record received quantities; link receipt to purchase order; inspect GRN/receipt history and discrepancies | Basic receive-goods path identified; full GRN workflow is a schema candidate |
| Stock movements | View movement history; record supported adjustments, receipts, sales, returns and transfers | Existing movement ledger identified; verify each UI/API action |
| Transfers | Create/validate stock transfer; dispatch from source; receive at destination; track in-transit quantities | To verify in code |
| Stock counts | Start/record physical inventory count; compare counted vs system quantity; approve/apply adjustments | Existing count/adjustment APIs identified; verify UI and lifecycle |
| Reservations | Reserve stock for an order; release on cancellation; inspect reserved quantity | Backend implementation proposed in PR #158; not merged/deployed |
| Fulfilment | Select stock location by delivery PIN; prepare shipment; partial/full dispatch; prevent overselling and duplicate deduction | PRs #158/#159 prepared; not merged/deployed |
| Returns and quality | Receive return; inspect; quarantine; restock or reject; record reason and disposition | Full workflow not yet implemented; schema candidate |
| Replenishment | Identify low stock; suggest/create replenishment or purchase request; select preferred vendor | To verify in code |

## Purchasing / Procurement

Trace and inventory each stage separately:
- Purchase request creation, line items, submission and approval/rejection.
- Vendor selection and vendor quotation request/receipt/comparison.
- Purchase order creation, editing, approval, sending and status tracking.
- Vendor dispatch / advance shipping information and expected delivery.
- Goods receipt / GRN, partial receipt, over/short/damaged quantity handling.
- Quality inspection and acceptance/rejection.
- Vendor invoice capture, matching against PO and receipt, bill creation.
- Bill approval, payment scheduling/execution and payment status.
- Vendor master, contacts, terms, pricing and purchase history.

**Status:** capability checklist to verify against actual screens, APIs and schema. Do not assume every listed step currently exists.

## Accounting

Trace and inventory each stage separately:
- Chart of accounts and account configuration.
- Journal entries: create, edit where allowed, post, reverse and view.
- General ledger and account balances.
- Customer invoices, credit notes and receipts.
- Vendor bills, debit notes and supplier payments.
- Payment allocation, refunds and reconciliation.
- Bank/cash accounts and bank reconciliation.
- Tax/GST configuration, input/output tax, returns and reports.
- Profit and loss, balance sheet, cash flow and trial balance.
- Period controls, audit trail and export.

**Status:** capability checklist to verify against actual screens, APIs and schema. Do not assume every listed step currently exists.

## Sales / Orders / Checkout

- Browse/search products and view product details.
- Cart management and quantity changes.
- Customer/contact and delivery address capture.
- PIN-code/serviceability and fulfilment-location selection.
- Pricing, discounts, coupons, shipping, tax and final total calculation.
- Order placement and payment initiation.
- Order listing, detail, status history, cancellation and refund handling.
- Manual order creation by authorised staff, including PIN-code capture and location resolution.
- Order-to-inventory reservation and fulfilment linkage.

**Status:** capability checklist; manual order PIN/location flow and all checkout actions must be traced and verified.

## Customers / CRM

- Customer list, search, profile and contact details.
- Create/update customer and address book.
- Customer order, payment and return history.
- Segmentation, notes, communication preferences and consent.
- Support enquiries, follow-ups and customer activity.
- Duplicate handling and privacy/role restrictions.

**Status:** capability checklist to verify.

## Payments / Gateway / Refunds

- Payment initiation and provider order/session creation.
- Success, pending, failed and cancelled payment states.
- Signed webhook/callback verification and idempotent processing.
- Order/payment reconciliation.
- Refund initiation, status and audit trail.
- Payment method/provider configuration and transaction reporting.

**Status:** capability checklist to verify. Never infer a genuine provider failure from an unverified client status or callback.

## Delivery / Logistics

- Shipment creation and stock-location association.
- Delivery assignment and tracking details.
- Picking/packing and dispatch.
- Partial dispatch and remaining quantity handling.
- Shipment status updates and status history.
- Delivery attempts, failure reasons, rescheduling and proof of delivery.
- Returns/pickups and reverse logistics.

**Status:** partial dispatch work is represented by PRs #158/#159; all other actions require code trace.

## POS

- POS session/register opening and closing.
- Product lookup/barcode scanning.
- Cart, quantity, discount and tax calculation.
- Customer selection or walk-in sale.
- Cash/card/UPI and split payment handling.
- Receipt printing/reprint and refunds/returns.
- Stock deduction and inventory movement linkage.
- Cash reconciliation and shift reporting.

**Status:** capability checklist to verify.

## Loyalty

- Programme and earning/redemption rule configuration.
- Customer enrolment and membership status.
- Points earn, redeem, expire and reverse.
- Wallet/points balance and transaction history.
- Rewards, tiers, coupons and campaign linkage.
- Order cancellation/refund adjustment.

**Status:** capability checklist to verify.

## Website / Storefront

- Homepage, navigation, category and product listing.
- Product detail, variants and availability.
- Search, filters and sorting.
- Cart and checkout.
- Customer account, login and order history.
- Content/banner/page management.
- SEO metadata and responsive presentation.
- Store configuration and publish/preview workflow.

**Status:** capability checklist to verify.

## HR / Payroll

- Employee records and organisation structure.
- Roles, departments and employment status.
- Attendance, shifts and leave.
- Payroll components, salary processing and payslips.
- Deductions, statutory calculations and payroll approvals.
- Employee self-service and reports.

**Status:** capability checklist to verify.

## Reports / Dashboard / Settings / Administration

- Dashboard KPIs and drill-down links.
- Sales, inventory, purchasing, accounting and customer reports.
- Date/location/status filters and export.
- User, role and permission management.
- Company, tax, currency, warehouse and operational settings.
- Audit logs, integration settings and system health.

**Status:** capability checklist to verify.

## Imports / Exports / Bulk operations

- Import products, categories, attributes and other supported master data.
- Download templates and export records.
- Validate file format, required fields, references and duplicates before writes.
- Preview errors and provide row-level feedback.
- Safe retry/idempotency and import history.
- Permission checks and audit trail.

**Status:** capability checklist to verify.

## Required module sign-off format

For each module, the completed audit must include:

1. **Module purpose** — what business job it performs.
2. **Feature/function list** — every visible user action, grouped by capability.
3. **Implementation trace** — screen/component -> frontend service -> API route -> backend service -> existing tables/columns.
4. **Access rules** — which roles can perform each action.
5. **Current result** — working, partially working, broken, missing, or not verified.
6. **Defects** — split into fix-without-schema and schema-required, with issue IDs in this register.
7. **Test evidence** — exact automated/manual checks performed and results.
8. **Dependencies** — linked modules and end-to-end workflows affected.

The function inventory describes intended/observed capability scope; it is not a claim that every function is already implemented or working.

# Module audit

## 1. Catalog

**Audit status:** NOT STARTED. Capability scope is documented below; no Catalog function has yet been verified end-to-end. This is the first module to trace.

### Schema-independent fixes
| ID | Issue / affected path | Evidence | Planned fix | Verification | Status |
|---|---|---|---|---|---|
| CAT-NOSCHEMA-001 | Pending full Catalog UI -> API -> backend -> schema trace | Not yet traced | Inspect existing implementation first; fix broken wiring, validation, rendering and queries that use existing schema | Targeted backend tests + frontend builds; runtime only if available | Candidate |

### Schema requirements
| ID | Requirement | Why existing schema is insufficient | Affected code | Dependencies / acceptance criteria | Status |
|---|---|---|---|---|---|
| CAT-SCHEMA-001 | None confirmed yet | Catalog audit not complete | TBD | Do not add a requirement until traced | Candidate |

## 2. Inventory and order fulfilment

**Audit status:** PARTIAL — initial code/schema reconnaissance completed; full screen-by-screen function audit and live-schema verification remain open.

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

**Audit status:** NOT STARTED. Capability checklist drafted; request -> approval -> quotation -> PO -> dispatch -> GRN -> quality -> invoice/bill -> approval -> payment flow still needs tracing.

### Schema-independent fixes
| ID | Issue / affected path | Evidence | Planned fix | Verification | Status |
|---|---|---|---|---|---|
| PUR-NOSCHEMA-001 | Pending full module trace | Not yet traced | Reuse existing purchasing APIs and PO structures; fix safe UI/API/validation gaps | Targeted tests/builds | Candidate |

### Schema requirements
| ID | Requirement | Why needed | Affected code | Acceptance criteria | Status |
|---|---|---|---|---|---|
| PUR-SCHEMA-001 | To be determined after trace | Do not assume GRN, invoice or approval schema is absent until existing tables and links are inspected | TBD | Record only confirmed gaps; reconcile shared GRN requirements with Inventory | Candidate |

## 4. Accounting

**Audit status:** NOT STARTED. Capability checklist drafted; accounts, journals, ledger, invoices, bills, payments, tax/GST and reconciliation flows still need tracing.

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
