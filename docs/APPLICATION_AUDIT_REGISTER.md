# Application Audit Register

> [!IMPORTANT]
> **LATEST AUDIT STATUS — 30 October 2026**
>
> **Overall: IN PROGRESS**
>
> **Latest update:** Initial Catalog UI/API trace is complete for core product, category, attribute, variant and image operations. Detailed edge-case and permission verification is still underway.
>
> **Latest confirmed findings:** Product-level attributes were not loaded/saved; category descriptions were omitted from the form; variant archive lacked stock/open-PO guards; required variant attributes and date/finite-number validation were incomplete. These schema-independent fixes are in draft PR #160. Latest CI run 41020173374 passed both frontend builds and backend unit tests; PostgreSQL 15/16 schema checks in run 41020173324 passed.
>
> **Catalog capability findings:** Product create/edit/archive/delete routes exist; category create/edit and nested category UI exist; attribute definitions can be created and option values appended; variants can be created/edited/archived; product images can be added by URL/upload and a primary image selected. Category deletion, attribute definition edit/deactivation, and image deletion/metadata editing were not found in the traced UI/API.
>
> **Critical open points:** Product creation still spans separate requests and can leave a partial product if a later operation fails. PR #160 has CI verification but is not merged/deployed and has no live runtime verification. No full module audit has signed off yet.
>
> **Current work:** PR #160 is draft and not merged/deployed. Inventory PRs #158/#159 remain draft and not merged/deployed.
>
> **Next action:** Continue Catalog audit through category hierarchy edge cases, attribute value validation, variant lifecycle, image upload configuration, role permissions and end-to-end tests. Fix safe gaps as they are confirmed; record any genuine schema requirement separately.
>
> **Production safety:** No production schema changes, merge or deployment have been performed as part of this audit.


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
| Catalog fixes (product attributes, category description, variant safety and validation) | <badge color="warning">FIXED IN DRAFT PR</badge> | PR #160 uses existing APIs/schema; GitHub Actions run 41020173374 passed both frontend builds and backend unit tests; PostgreSQL 15/16 schema checks also passed; not merged/deployed or live-verified |
| Catalog audit | <badge color="warning">PARTIAL</badge> | Core UI/API trace completed; edge cases, permissions, runtime and full end-to-end sign-off remain |
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

**Audit status:** IN PROGRESS — initial repository-level UI/API trace completed for core product, category, attribute, variant and image operations. Edge cases, permissions, live schema and end-to-end verification remain.

### Catalog capability trace (repository evidence)

| Capability | Frontend / API evidence | Current audit result |
|---|---|---|
| List/search products | Product list in `CatalogueWorkspace.jsx`; `GET /catalogue/products` | List exists; search UI not observed in the traced workspace |
| Create product | `ProductCreateForm.jsx`; `POST /catalogue/products` | Implemented as a multi-request flow; partial-save risk recorded below |
| Edit product | Product form; `PUT /catalogue/products/{id}` | Core fields and category assignments wired |
| Archive product | Product action; `POST /catalogue/products/{id}/archive` | Implemented |
| Permanently delete product | Owner/admin UI action with required reason; `DELETE /catalogue/products/{id}`; deletion audit insert | Implemented with role and FK protections |
| Create category / subcategory | Category form; `POST /catalogue/categories` with optional `parent_id` | Implemented; nested hierarchy supported |
| Edit category / subcategory | Category form; `PUT /catalogue/categories/{id}` | Implemented; backend prevents self/descendant nesting |
| Delete/archive category | No category delete/archive UI action or endpoint found in traced files | Not available in traced implementation; confirm desired lifecycle policy |
| Create attribute definition | `CatalogueVariantsPanel.jsx`; `POST /catalogue/attributes` | Implemented |
| Edit/deactivate attribute definition | No edit/deactivate action or endpoint found in traced files | Not available in traced implementation |
| Add attribute options | `PUT /catalogue/attributes/{id}/options` | Append-only options operation; removal/replacement not available in traced UI/API |
| Save product-level attribute values | Existing backend `GET /catalogue/products/{id}/attributes` and `PUT /catalogue/products/{id}/attributes/{attribute_id}` | Form previously did not load/save these values; fix prepared in PR #160 |
| Create variants | Product form and variants panel; `POST /catalogue/products/{id}/variants` | Implemented; duplicate combination checks and generated SKU logic exist |
| Edit/archive variants | Variants panel; `PUT /catalogue/variants/{id}`, `POST /catalogue/variants/{id}/archive` | Implemented |
| Add product/variant images | `ProductImagesPanel.jsx`; image URL and upload endpoints | Implemented; file upload requires configured object storage |
| Set primary image | `PUT /catalogue/products/{id}/images/{image_id}/primary` | Implemented |
| Delete image / edit image metadata | No delete or general metadata-update endpoint/action found in traced files | Not available in traced implementation |
| Availability restrictions | Product form; `GET/PUT /catalogue/products/{id}/availability-rules` | Implemented for channel, region, PIN and stock location; further precedence behaviour needs testing |

### Schema-independent fixes / defects

| ID | Issue / affected path | Evidence | Planned fix | Verification | Status |
|---|---|---|---|---|---|
| CAT-NOSCHEMA-001 | Core Catalog UI/API trace | `CatalogueWorkspace.jsx`, `ProductCreateForm.jsx`, `CatalogueVariantsPanel.jsx`, `ProductImagesPanel.jsx`, `backend/app/api/catalogue.py` and `backend/tests/test_catalogue.py` inspected | Continue edge-case, role, validation and end-to-end audit | Remaining | In progress |
| CAT-NOSCHEMA-002 | Product-level attribute values not loaded/saved by product form | Form only processed variant attributes; existing backend GET/PUT routes already support product-level values | Load saved product attribute values on edit; persist scalar/multi-select values using existing endpoint; apply matching controls and required validation | PR #160; GitHub Actions run 41020173374 passed both frontend builds and backend unit tests | Fixed in draft PR; not merged/deployed |
| CAT-NOSCHEMA-003 | Product create spans separate API requests for product, options, variants and later availability | `ProductCreateForm.jsx` sends sequential requests; catch block explicitly warns product may have been created while later operations failed | Design a safe transactional application-level save using existing schema, or make partial progress/retry state explicit; preserve existing records | Not started | Confirmed |
| CAT-NOSCHEMA-004 | Attribute definitions cannot be edited/deactivated; option lists are append-only | Traced UI and backend routes expose create and append-options only | Determine required edit/deactivation semantics and protect options already used by variants/product values | Not started | Confirmed capability gap |
| CAT-NOSCHEMA-005 | Product images cannot be deleted or metadata edited after creation | Traced image UI/API exposes list, add/upload and set-primary only | Define safe image removal/metadata-edit lifecycle; check storage object cleanup implications before implementation | Not started | Confirmed capability gap |
| CAT-NOSCHEMA-006 | Category description is supported by backend model/API but omitted from category form payload/UI | Category API model includes description; workspace form previously submitted only name, slug and parent_id | Add description field to create/edit UI and send it through existing endpoint | PR #160; GitHub Actions run 41019662093 passed both frontend builds and backend unit tests | Fixed in draft PR; not merged/deployed |
| CAT-NOSCHEMA-007 | Category deletion/archive is not exposed in traced UI/API | Categories have active-state fields, but no category lifecycle endpoint/action was found in traced files | Confirm whether categories should be archived; define handling for child categories and product assignments before implementing | Not started | Confirmed gap; policy decision pending |
| CAT-NOSCHEMA-008 | Variant archive did not check on-hand/reserved stock or open purchase quantities | `archive_variant` updated `is_active=false` without the stock/PO guards already used when replacing an empty default variant | Reject archive while stock remains or open purchase quantities exist; return actionable conflict messages | PR #160; GitHub Actions run 41020173374 passed backend tests | Fixed in draft PR; not merged/deployed |
| CAT-NOSCHEMA-009 | Required variant attributes and strict attribute value validation were incomplete | Create/update variant APIs did not enforce required variant attributes; date validation checked only string shape; numeric validation accepted non-finite floats | Enforce required variant attributes at API level; require real ISO dates and finite numbers; add focused unit tests | PR #160; GitHub Actions run 41020173374 passed backend tests and both frontend builds | Fixed in draft PR; not merged/deployed |

### Schema requirements

| ID | Requirement | Why existing schema is insufficient | Affected code | Dependencies / acceptance criteria | Status |
|---|---|---|---|---|---|
| CAT-SCHEMA-001 | None confirmed in the initial Catalog trace | Core gaps identified so far appear addressable with existing tables and endpoints; live schema is not verified | TBD | Continue audit; add only if a real schema dependency is proven | No confirmed requirement |

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
