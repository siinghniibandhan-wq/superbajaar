# Important project updates

> [!IMPORTANT]
> ## LATEST AUDIT STATUS — SCHEMA REVIEW
> **Status:** IN PROGRESS — schema dependency mapping completed at repository level; application/security/workflow audit underway; production schema state NOT VERIFIED.
>
> **Latest critical findings:** (1) runtime route registration remains unresolved: repository `main.py` mounts 11 routers, but a prior runtime check reported only 16 routes; verify deployed commit/import path/OpenAPI before release. (2) PR #158 allows website checkout without a PIN to bypass stock reservation, and a customer can submit an arbitrary `location_id`; treat both as merge blockers for stock protection. (3) a non-owner admin can demote/deactivate another owner when another active owner exists; (4) manager/staff roles have backend permissions but the frontend blocks them from the admin console; (5) the protected migration runner's post-migration health failure is alert-only and does not itself force a non-zero exit; (6) active `backend/schema/` coexists with historical `database/migrations/` and `database/schema.sql`, creating a dual-source-of-truth risk. Production `sb_app` ledger/checksums, runner `--status`, and backup readiness remain NOT VERIFIED. No application or schema fixes were made.
>
> **Repository review completed so far (2026-10-30):**
> - Confirmed the schema directory currently has eight SQL files: one baseline and seven additive migrations. The migration filenames are `000_baseline_schema.sql`, `009_loyalty_programme.sql`, `009_product_availability_delivery.sql`, `010_customer_accounts_referrals.sql`, `011_customer_phone_uniqueness.sql`, `012_product_category_assignments.sql`, `012_variant_image_primary.sql`, and `013_product_deletion_audit.sql`.
> - The duplicated `009` and `012` prefixes are the exact four documented legacy files; the workflow explicitly protects these pairs. Do not rename, reorder, or reuse those prefixes.
> - Confirmed every non-comment entry in `backend/schema_required.txt` maps to a file in `backend/schema/`. `011_customer_phone_uniqueness.sql` is intentionally omitted according to its own note because application validation handles duplicate mobile numbers; its unique index is therefore not a required deploy gate.
> - The required list includes the baseline, loyalty, product availability, customer/referral, product-category assignment, primary-image, and product-deletion-audit migrations. This is consistent with the files present, but does not prove their production ledger checksums or successful application.
> - Reviewed the migration workflow: scratch PostgreSQL 15 and 16, applies the full schema set twice, checks the protected legacy filenames, required-file references, phone uniqueness behaviour, and migration-runner safety tests. CI is not a production-ledger check.
> - Reviewed the baseline: it creates legacy and current-generation tables side by side, including separate legacy/current product and order structures. `CREATE TABLE IF NOT EXISTS` will not reconcile an already-existing table's columns, constraints, or ownership. The baseline is explicitly an empty-database bootstrap, not a repair migration.
> - The baseline's inventory and order foundation includes `stock_locations`, `inventory_balances`, `inventory_movements`, `orders`, `order_lines`, and `deliveries`. The two order-fulfilment PRs reviewed so far reuse these existing objects; no new schema file is indicated by that code path.
> - The loyalty migration adds `orders.customer_email` and loyalty tables; customer/referral migration adds customer accounts, sessions and referral tracking; product availability migration adds channel flags and scoped availability rules; the two `012` files add category assignments and primary-image selection; `013` adds a product deletion audit table with narrow conditional grants.
> - Governance is explicit: the Database Owner owns SQL, migration numbering, `schema_required.txt`, runner and CI database checks. ChatGPT is the secondary reviewer, not the Database Owner. This audit therefore records findings and recommendations only; it does not author or alter SQL/protected database assets.
> - PR #158's order-reservation implementation uses existing baseline objects plus `orders.customer_email` from the required loyalty migration. No new schema file is indicated by the reviewed code.
> - Static review does not prove live compatibility or application status. The live `sb_app` ledger, checksum comparison, runner `--status`, and backup readiness remain NOT VERIFIED.
>

> **Latest schema-to-application dependency findings (static review; application audit now underway):**
> - Confirmed the active backend API modules query the current-generation model: `products`, `product_variants`, `product_images`, `product_category_assignments`, `inventory_balances`, `inventory_movements`, `orders`, `order_lines`, `deliveries`, `payments`, `customers`, `support_cases`, `suppliers`, `purchase_orders`, and `purchase_order_lines`. The baseline plus required migrations reviewed so far provide these objects.
> - Confirmed the application-specific schema dependencies: catalogue uses `009_product_availability_delivery.sql`, `012_product_category_assignments.sql`, `012_variant_image_primary.sql`, and `013_product_deletion_audit.sql`; staff auth uses baseline `app_users`/`app_user_sessions`; customer auth/referrals use `010_customer_accounts_referrals.sql`; loyalty uses `009_loyalty_programme.sql`; purchasing and inventory use baseline tables.
> - Documentation drift: `backend/app/api/auth.py` and `auth_middleware.py` still describe auth storage as migration 007; `backend/app/api/purchasing.py` still describes purchasing as migration 006. The current schema directory has no 006 or 007 files; the relevant tables are in the baseline. These are stale references, not evidence that a migration is missing. Do not create replacement migrations on this basis.
> - Data preflight risks confirmed from DDL: `012_variant_image_primary.sql` can fail if a product/variant gallery already has multiple rows marked primary; `011_customer_phone_uniqueness.sql` can fail if canonicalised phone numbers collide. The latter is intentionally non-required, but its failure should still be visible in runner status.
> - `012_product_category_assignments.sql` performs a backfill from `products.category_id`; its conflict handling makes repeat application safe. The baseline's `products` table is the current catalogue table; `products_legacy` is a separate older model and is still referenced by legacy `inventory`, `price_history`, and `order_items`.
> - The purchasing endpoints use baseline `purchase_orders`/lines and update inventory balances/movements in one transaction. No dedicated GRN, vendor invoice, bill, or payment-to-vendor schema objects were found in the reviewed baseline/migrations; the current purchasing API is a narrower purchase-order-and-receipt foundation, not the full procurement lifecycle.
> - Backend route configuration currently sets `api_prefix=/api`, matching the migration runner's default health URL `http://127.0.0.1:8001/api/health`. This is a repository configuration observation only; it does not verify the live server.
> - All findings above are static source review. No live data was queried, no SQL was executed against production, and production migration/backup status remains NOT VERIFIED.


> **Application audit — first cross-module findings (IN PROGRESS):**
> - Inventory issue/scrap and physical-count endpoints write positive `inventory_movements.quantity` with `movement_type='adjustment'`. The movement row stores a reference label/note but no signed direction or before/after quantity. A movement-only ledger therefore cannot independently distinguish stock-in from stock-out or a positive from negative count variance. This is an application/data-model semantics finding; no schema fix is proposed before the full audit and owner approval.
> - Main-branch order creation currently writes order headers and lines but does not itself reserve stock. The reservation/fulfilment work is in pending PR #158, not in the reviewed `main` baseline. Do not describe reservation as merged or production-active.
> - Current purchasing API supports suppliers, draft/approve-to-ordered purchase orders, partial receipt and inventory posting. The documented larger procurement stages (vendor quotation, dispatch, quality check, vendor invoice/bill and payment) are not represented by the reviewed purchasing tables/endpoints; treat those stages as unimplemented/not verified rather than assuming the UI completes them.
> - Payment API deliberately records application payment entries only; it blocks manual captured/refunded transitions absent verified provider confirmation. Its reconciliation endpoint explicitly disclaims bank/gateway settlement reconciliation. This is an acknowledged integration limitation, not a missing payments table.
> - Customer and staff authentication use separate current-generation tables and session tables. The code and baseline/migration objects align statically; the stale 006/007 migration comments are documentation drift noted above.
> - These are preliminary findings from a partial backend review. Frontend-to-API mapping, role/permission coverage, all remaining backend modules, tests, and pending PR branches still need review. No test suite or production endpoint was executed in this static audit.


> **Frontend/module audit — initial scope confirmation (IN PROGRESS):**
> - The admin router exposes 15 workspaces: Dashboard, Catalogue, Pricing, Orders, Payments, Inventory, Purchasing, Delivery, POS, Customers/CRM, Loyalty, Accounting/Tax, HR/Payroll, Reports and Settings. The module launcher and router distinguish these entry points, but a workspace being visible does not mean its full business workflow is implemented.
> - Accounting currently reads orders, payment records and catalogue tax-rate fields. Its own screen says it does not post journals, calculate GST liability, reconcile bank statements or file returns. It is an operational summary, not an accounting ledger/tax engine.
> - HR currently reads and updates staff application accounts/roles through `/auth/users`. Its own screen says employee records, attendance, salary structures, payslips and payroll are not enabled.
> - Pricing currently edits variant selling price, MRP and cost price. Promotion rules are explicitly not enabled.
> - Reports and Dashboard are snapshots assembled from a small set of existing APIs, not a separate reporting/analytics model. Dashboard/Reports cap requests at 500 records and should not be treated as complete all-time reporting without pagination/aggregation.
> - POS currently creates an order and then a pending payment record as two separate API operations. The UI explicitly warns that it did not charge a gateway or confirm cash. If the second call fails, the order remains created and the UI asks the operator not to retry blindly. Pending PR #158 adds a stock-location/reservation workflow; it is not part of main until merged.
> - Purchasing frontend mirrors the implemented supplier/PO/receipt API only. Delivery frontend consumes shipment/order/location APIs. Inventory frontend consumes balances, movements, adjustments, issues, counts and transfers. Full end-to-end cross-module verification remains pending.
> - These observations come from source inspection only. No browser interaction, live API calls, test execution or deployment verification occurred in this review.


> - Frontend Loyalty workspace is currently a customer/order-spend summary and explicitly says it does not issue or store points. The backend does contain loyalty rules/accounts/transactions/redemption-allocation tables and loyalty APIs; rule/account administration appears under Settings. This is a frontend capability/placement gap, not evidence that the loyalty schema is absent.
> - Admin Settings exposes user management plus loyalty rule/account administration. HR also exposes staff user management, so there is overlap between Settings and HR that should be clarified in the module ownership audit; HR is not a payroll subsystem.
> - The frontend POS currently does not create a delivery record as part of checkout. Delivery is a separate operational workspace. Stock reservation and location selection are pending in PR #158; delivery lifecycle UI changes are pending in dependent PR #159.


> **Pending pull-request verification refresh (2026-10-30):**
> - PR #158 head `98f9e43b3c9cf70904dd8bb41ab1676038f47919`: GitHub Actions `Super Bajaar CI` and `Database files check` both completed successfully. PR remains open/draft/unmerged. No production DB or deployment verification.
> - PR #159 head `03b293fb701d31efdc32adb687b92707c42d2d6b`: `Super Bajaar CI` completed successfully. PR remains open/draft/unmerged and depends on #158.
> - PR #160 head `fc86d91ae54aac44438ed316b8190ac76a234652`: `Super Bajaar CI` and `Database files check` both completed successfully. PR remains open/draft/unmerged. Category changes remain outside the audit scope unless specifically authorised.
> - CI success is limited to the tested commits and disposable CI environments; it does not establish production migration status or live runtime correctness.


> **Schema dependency matrix — static repository mapping:**
> | File | Objects/changes | Application consumers | Required gate |
> |---|---|---|---|
> | `000_baseline_schema.sql` | Current + legacy user/customer/catalogue/order/inventory/delivery/payment/purchasing/support tables and core constraints/indexes | Most backend APIs | Yes |
> | `009_loyalty_programme.sql` | `orders.customer_email`, loyalty rules/accounts/transactions/redemption allocations, partner enquiries | Orders, loyalty, customer registration, settings | Yes |
> | `009_product_availability_delivery.sql` | Product POS/website flags, delivery options, scoped availability rules | Catalogue/storefront | Yes |
> | `010_customer_accounts_referrals.sql` | Customer accounts/sessions/referrals | Customer auth, auth middleware, order/referral rewards | Yes |
> | `011_customer_phone_uniqueness.sql` | Canonical-phone expression unique index | Customer registration duplicate guard | No — intentional optional gate |
> | `012_product_category_assignments.sql` | Multi-category assignment table and primary-category backfill | Catalogue list/create/update | Yes |
> | `012_variant_image_primary.sql` | `product_images.is_primary` and one-primary-per-gallery partial unique index | Catalogue image management/listing | Yes |
> | `013_product_deletion_audit.sql` | Product deletion audit table and conditional narrow grants | Catalogue product deletion | Yes |
>
> This matrix maps repository DDL to inspected API references; it is not a production inventory. The legacy/current parallel tables remain a separate compatibility concern, and no data migration or consolidation is authorised by this audit.


> - Main-branch backend `app/services/` contains only `__init__.py`; business rules and SQL are largely implemented directly inside API route modules. PR #158 introduces `services/order_inventory.py` for its new reservation workflow. This is an architecture/maintainability divergence from the documented service/repository layering; do not refactor unrelated modules during this audit.
> - Current backend test inventory includes auth, access-control, catalogue, customer auth, customers, delivery, health, inventory, orders, payments and purchasing tests. No dedicated `test_loyalty.py` or service/repository integration test module is present in the main test directory. Test existence alone does not prove end-to-end coverage; inspect assertions and gaps before final severity grading.


> **Security and access-control audit — priority findings (static review):**
> - **HIGH — owner-account protection gap:** `backend/app/api/auth.py::update_user` restricts non-owner admins from assigning the `owner` or `admin` roles, but it does not reject a non-owner admin changing an existing owner's role to a lower role or deactivating that owner when another active owner exists. The “last active owner” guard only prevents removal of the final owner. This conflicts with the stated owner-only privilege boundary. Requires a targeted authorization fix and regression tests; no code changed in this audit.
> - **HIGH — customer identity is not verified at registration:** `POST /api/customer-auth/register` accepts a new email/mobile and creates an account/session without email OTP, SMS OTP, or another proof-of-control step. The duplicate/legacy-record checks help prevent duplicates but do not prove the registrant controls those contact details. Assess account-squatting, referral abuse and recovery implications before launch.
> - **MEDIUM — public support-ticket intake has no visible application-level throttling or bot challenge:** `POST /api/customers/support-portal/tickets` is intentionally unauthenticated and can create a customer record plus support case. Payload validation and exact-match protection for existing customer contacts exist, but rate-limit/bot-abuse controls were not found in the reviewed route/middleware.
> - **MEDIUM — customer loyalty account lookup relies on order reference + email:** `GET /api/loyalty/customer/account` is public by middleware policy and returns loyalty account details/ledger after matching both values to an order. Order references are UUID-derived 12-hex suffixes, but there is no visible throttling/attempt control in the reviewed code. Review whether this endpoint should require a signed-in customer session instead.
> - **MEDIUM — referral copy conflicts with reward policy:** `customer_auth.py::referrals` returns a fixed statement that both parties receive 100 coins after first delivery; actual order-delivery code issues rewards under a referral-status update. Confirm the advertised eligibility and conditions match the real award rules, and that failed/returned/cancelled orders cannot qualify.
> - Existing access-control tests exercise the role-path helper, but the main test inventory has no dedicated regression test for admin-vs-owner changes to an existing owner, no `test_loyalty.py`, and no dedicated public abuse/rate-limit tests. These are test coverage gaps, not proof that every related path is broken.
> - The global request dependency authenticates staff/customer sessions and applies the role path matrix before route execution. Staff writes are intentionally narrow; managers can write operational modules; catalogue and staff-user administration remain owner/admin-only. This is a static policy review and has not been tested against a live identity/database.
> - The above findings are based on `main` source at the reviewed commit. They are not fixes, do not modify schema requirements, and have not been exercised against production.


> **Inventory, procurement and fulfilment audit — additional findings:**
> - **HIGH — inventory movement ledger cannot independently reconstruct stock:** receipt/adjustment, issue, scrap and physical-count variance are stored using `movement_type='adjustment'` with positive `quantity`; issue/count paths reduce or may increase the balance separately. The signed variance is returned by the count API but not persisted in the movement row. Reconciliation from movements alone is therefore ambiguous. Current balance writes are transactional, but the ledger lacks unambiguous directional semantics. Treat this as a material auditability/control gap; any redesign needs a separate owner-approved change request, not an ad hoc migration.
> - **HIGH — order/shipment lifecycle is not fully synchronised:** delivery shipment status transitions and order status transitions are separate APIs. Even in pending PR #158, dispatch consumes reserved inventory in the delivery endpoint, but setting a shipment to `delivered` does not itself transition the parent order to `delivered`. Loyalty earn/referral awards are triggered by the order status endpoint, so a shipment completed only through the Delivery workspace can leave the order unreconciled and rewards unissued. Define one authoritative lifecycle transition and idempotent cross-module tests before production enablement.
> - **MEDIUM — delivery provider integration is absent:** delivery records and status history are internal manual workflow only; no carrier booking, tracking webhook, proof-of-delivery, or external status confirmation is implemented in the reviewed delivery API.
> - **MEDIUM — purchasing receipt is not a full GRN control:** PO receipt updates ordered/received quantities, inventory balances and movement ledger in one transaction, but there is no separate goods-receipt document/header, quality inspection/rejection workflow, vendor invoice/bill matching or vendor payment settlement. This matches the narrower scope already recorded; do not represent it as a complete procure-to-pay workflow.
> - **MEDIUM — purchasing and inventory backend tests are mostly request validation and missing-configuration checks:** reviewed tests do not exercise the full database transaction paths for PO approval/partial receipt, inventory adjustment/transfer/count, or role-protected operations against a disposable PostgreSQL application schema. CI schema-file checks are separate from these app integration scenarios.
> - **PR #158 review note:** it adds stock reservation and dispatch transaction helpers and locks the parent order during shipment creation/status changes, reducing duplicate-shipment and concurrent dispatch risk. It does not resolve the delivery-to-order delivered-state synchronisation finding above. Its own CI success does not establish this lifecycle behaviour against a real PostgreSQL deployment.
> - No code, schema, migration runner, required schema list or production data changed as part of this review.


> **Admin/storefront and role-coverage audit — further findings:**
> - **HIGH — operational roles cannot enter the admin console:** Settings/API support `manager`, `staff` and `viewer` accounts, and backend middleware grants managers/staff selected operational write permissions. However, `frontend/src/app/router.jsx` blocks every signed-in user except `owner` and `admin` before rendering any workspace. Thus the manager/staff/viewer roles cannot use the UI for the API permissions they are assigned. Resolve the intended role-to-workspace access policy before enabling these roles.
> - Storefront customer sessions use a separate token key and explicitly pass the customer bearer token; website checkout requires customer sign-in and the backend enforces that the order email matches the signed-in account. The public storefront has customer registration/login, cart, serviceability, support portal and loyalty views. Customer email/mobile verification remains the identity gap recorded above.
> - Storefront checkout currently creates an order only and explicitly states online payment is not enabled. POS creates an order and then separately attempts to create a pending payment record; it does not charge a gateway or confirm cash. The two-step POS flow can leave an order without a payment row if the second request fails; the UI correctly warns operators not to blindly retry.
> - The admin router has 15 workspaces, but several visible module descriptions overstate the actual implemented scope (e.g. Pricing & Promotions, Accounting & Tax, HR & Payroll, Loyalty & Rewards). Their workspaces disclose the limitations in their content; align launcher descriptions and permissions with actual capability before launch.
> - Storefront cart, wishlist, customer profile details and customer/staff bearer tokens are stored in browser localStorage. This is a common implementation pattern but increases exposure if any script-injection/XSS issue is present. Confirm a deliberate token-storage/XSS policy and CSP/security-header coverage before production.
> - PR #158 adds reservation/dispatch logic but its current order and delivery APIs still have independent status state. It also retains legacy no-reservation behaviour for orders with neither a delivery PIN nor explicit stock location. Treat those as explicit compatibility cases that need operator-facing visibility and tests.


> **Correction and schema-source inventory (important):**
> - Correction to the earlier wording: files named `006_purchasing.sql` and `007_access_control.sql` do exist under the historical `database/migrations/` directory. They do **not** exist in the active `backend/schema/` directory and are not listed in `backend/schema_required.txt`. The current runner is invoked against `backend/schema/`; the legacy directory is a separate historical migration set. References in API modules/bootstrap scripts to “migration 006/007” are therefore ambiguous/stale relative to the current active schema workflow, not proof those historical files are absent from the repository.
> - The repository currently contains three SQL asset locations: `backend/schema/` (active runner/required-list path), `database/migrations/` (legacy numbered migration set 002–007), and `database/schema.sql` plus `database/seed.sql` (older reference schema/seed). No current deployment runner reference to the latter two locations was found in the inspected README/workflow/runner. Do not execute or delete these legacy/reference assets; their ownership, archival status and divergence from the active baseline need an explicit owner decision.
> - The legacy `database/migrations/002_orders.sql`–`007_access_control.sql` create tables that are now represented in the active baseline/current migrations. This creates a dual-source-of-truth risk if a contributor follows old module comments and applies the historical migration set independently. Active schema changes must continue only through `backend/schema/` and its approved runner.
> - Governance inconsistency: the header of protected `backend/scripts/apply_schema.sh` says “Owner: Claude by default”, while `docs/DATABASE_CHANGE_RULES.md` defines the human Repository/Database Owner as sole SQL/schema owner and ChatGPT as Secondary Reviewer. Do not edit the protected runner; Database Owner should decide whether this comment needs a separately authorised correction.
> - Additional documentation drift: `docs/api-contracts.md` describes `/api/health` as liveness-only, but the current health handler performs a database connection check and returns 503 when the database is unavailable. `backend/scripts/bootstrap_owner.py` and several API docstrings still refer to historical migration 007/006. Correct documentation only after the full audit and owner review.
> - `backend/tests/smoke_test.py` is a manually invoked read-only API smoke test requiring environment credentials; CI's `pytest tests/test_*.py` command does not collect it because its filename is `smoke_test.py`. Do not describe it as an automatically executed CI gate.
> - Architecture package inventory on `main`: `backend/app/models`, `schemas`, `repositories`, `integrations`, `middleware`, `utils`, and `services` contain only package initialisers; database access and most domain orchestration currently live in API modules. The target architecture document describes these as intended layers, so current implementation is materially less layered than the documented target.


> **Operational controls and audit-trail review — additional gaps:**
> - **MEDIUM/HIGH — purchase-order maker/checker separation is absent:** the same manager role can create a draft purchase order and call the approval endpoint to move it to `ordered`. The current PO model/API does not record a distinct requester/approver identity or approval event. If the business requires independent approval, the present role-path policy does not enforce it.
> - **MEDIUM — stock movement actor attribution is not populated:** the baseline `inventory_movements` table has a `created_by` field, but reviewed inventory, purchasing receipt and order-reservation/fulfilment inserts do not populate it. Stock movement records therefore do not identify the staff account responsible for the action. Order/delivery status history records also do not capture an actor in the reviewed schema/API.
> - **MEDIUM — physical count and stock adjustment are immediate writes:** the count endpoint directly overwrites `inventory_balances.on_hand` after checking reserved stock; it does not create a count session, submit/review/approve a variance, or preserve a before/after approval record. Managers can write inventory operations under the current role matrix. Confirm whether this is acceptable for launch controls.
> - These are control/auditability findings from source and schema inspection. They are not recommendations to immediately add columns/tables; first confirm required segregation-of-duties and audit-retention policy with the Database Owner/business owner.


> **Catalogue/media and deployment-boundary review:**
> - **MEDIUM — CORS permits every HTTPS Amplify app hostname:** `backend/app/main.py` combines configured explicit origins with a regex accepting arbitrary HTTPS subdomains of `amplifyapp.com`, while allowing credentials. This is broader than a single approved Super Bajaar frontend origin. Confirm the exact production origins and narrow the allowlist in a separately authorised security change; no CORS setting was changed.
> - **LOW/MEDIUM — object-storage orphan possibility:** image upload writes the object to S3, then opens a separate database transaction to create the gallery row. If the DB insert/unique-primary constraint fails after S3 upload, the object can remain orphaned. Consider cleanup/compensation and an orphan sweep in the media workflow; this is not a schema blocker.
> - PR #160 includes a row lock around attribute-option updates to avoid concurrent appends overwriting one another. The main branch reviewed here does not yet contain that change; PR #160 CI passed, but it remains unmerged. Category-related changes in that PR remain outside the authorised edit scope.
> - The only external provider integration found in the active backend package is inline AWS S3 object storage use in the catalogue router. A dedicated `backend/app/integrations` package contains no provider implementation. No payment-gateway, carrier, SMS/email verification, bank feed, or accounting-provider adapter was found in the reviewed code.


> **PR #158 — additional HIGH-priority stock-reservation review:**
> - **HIGH — website checkout can bypass stock reservation:** the customer storefront marks Delivery PIN optional and submits `delivery_pin=null` when blank. In PR #158, `reserve_order_stock()` intentionally returns without reserving when both PIN and location are absent. Therefore a normal website order can still be accepted without reserving inventory, leaving an oversell path. The website checkout policy needs an explicit decision: require a valid serviceable PIN before order creation/reservation, or implement another authoritative stock-location selection. Do not treat PR #158 as complete stock protection until this is closed.
> - **HIGH — customer can choose an arbitrary stock location through the API:** PR #158 adds `location_id` to `OrderCreate` and passes it into `reserve_order_stock()` for every channel. The customer-checkout branch validates website channel and account email but does not reject `location_id`; the helper accepts any active selected location when no delivery PIN is supplied. A customer can therefore craft a website order with a location ID and no PIN to reserve stock at a location they did not select through the storefront and that may not serve their address. Enforce channel/role-specific location policy server-side; POS should use staff-selected location, website should derive/validate location from serviceability, and public customers must not select arbitrary stock locations.
> - These findings are from direct static review of PR #158 head `98f9e43b3c9cf70904dd8bb41ab1676038f47919` and the main storefront checkout form. They are not covered by the current PR tests, which check POS location selection but not customer checkout without PIN or a forged location ID. Treat both as merge blockers for stock reservation unless the business owner explicitly accepts the legacy no-reservation path for website orders.


> **Loyalty transaction integrity review:**
> - **MEDIUM — manual loyalty earn endpoint does not verify the source order:** `POST /api/loyalty/admin/earn` is admin-only and idempotent by the caller-supplied `order_reference`, but the reviewed handler does not look up that order or verify its persisted status is delivered before crediting coins. It accepts caller-supplied eligible amount and delivered timestamp. Clarify whether this is intended as a manual adjustment; if so, it needs explicit adjustment reason/actor audit and a distinct permission, otherwise bind it to a real delivered order.
> - **MEDIUM — loyalty customer lookup endpoint remains public:** `GET /api/loyalty/customer/account` is exempted from global authentication and reveals account/card/transaction details after matching an order reference and email. The storefront currently uses the signed-in `/loyalty/customer/me` endpoint instead. Review whether the older order-reference lookup should remain enabled, and add throttling/monitoring if retained.
> - No dedicated loyalty API regression test file was found on main. CI passing backend tests does not establish FIFO redemption, expiry, idempotency, or referral award behaviour against PostgreSQL.


> **Inventory replenishment and supplier workflow check:**
> - The Inventory workspace's replenishment watchlist is informational only: it lists balances at or below five available units and tells the operator to raise a PO in Purchasing. It does not create or prefill a purchase order from the watchlist.
> - The reviewed baseline/API/UI have supplier records and PO supplier selection, but no preferred-supplier mapping per product/variant was found. Supplier choice is manual at PO creation.
> - These are feature-scope gaps relative to an automated low-stock → preferred-vendor replenishment workflow. They do not imply the current stock or PO tables are missing; record as application requirements for later prioritisation, not an immediate schema change.


> **Migration runner/release-gate semantics — review-only finding:**
> - **MEDIUM/HIGH — post-migration health failure is alert-only:** `apply_schema.sh` logs/alerts when its configured `/api/health` check is not HTTP 200, but it does not add that failure to `FAILED_NOW`, change the result classification, or force a non-zero exit. A caller that relies only on the documented 0/11 exit codes could continue its deployment flow after an unhealthy health check. Database Owner should confirm the systemd/deployment caller independently blocks on this alert or approve a protected-runner change; do not modify the runner in this audit.
> - **MEDIUM — status exit code treats optional pending files as attention:** `--status` exits 10 if any file is pending/failed/changed, even when all required files are applied; apply mode can return 11 when only non-required files fail. The 011 phone index is intentionally optional, so the release-gate procedure should explicitly interpret required-vs-optional output rather than assume every non-zero status means a required schema dependency is missing. Current documentation errs on the safe side by instructing the owner to stop on non-zero.
> - These findings are based on the protected runner's static control flow and documented exit-code policy. No runner command was executed against production and no runner file was edited.


> **DDL inventory count — active `backend/schema/` only:**
> - Static parser inventory across the eight active files: **40 table definitions**, **32 explicit index definitions**, **6 explicit sequence definitions**, and **3 `ALTER TABLE` statements**. The 40 tables include both current and legacy generations; they are not 40 active business entities.
> - The three alterations are the loyalty migration's `orders.customer_email`, the product-availability migration's product channel/availability columns, and the primary-image migration's `product_images.is_primary`.
> - The table inventory includes both current tables (e.g. `products`, `product_variants`, `orders`, `order_lines`, `app_users`, `customer_accounts`, `loyalty_*`) and historical/legacy tables (e.g. `products_legacy`, `orders_legacy`, `users`, `inventory`, `order_items`, `price_history`, `tickets`). Current API modules predominantly use the current-generation set; legacy tables remain in the baseline for compatibility/data preservation.
> - Counts are static DDL-definition counts, not a query of the live PostgreSQL catalog and not proof that the same number of objects exists in production.


> **Customer identity/CRM data-boundary finding:**
> - **MEDIUM — customer account, CRM profile and order identity are not unified:** registration inserts into `customer_accounts` and creates a `loyalty_accounts` row, but the reviewed registration path does not create/update `customers`; website order creation stores `customer_email` and contact fields on `orders` but does not link an order to a stable customer ID or upsert the CRM `customers` record. The CRM workspace reads `customers`, while customer sign-in/referrals use `customer_accounts`. A customer who registers and orders may therefore not appear in CRM until a separate support/customer operation creates a CRM record, and contact changes can diverge across tables.
> - This is a domain-identity/data-consistency gap, not a reason to merge tables immediately. Define the canonical customer identity and migration/backfill policy before any schema proposal; preserve existing legacy customer/order data.


> **Runtime route-registration discrepancy — NOT VERIFIED:**
> - Static `main` source imports and mounts 11 API routers (health, catalogue, inventory, orders, payments, delivery, customers, purchasing, staff auth, customer auth and loyalty) under the configured `/api` prefix. The compatibility entry point `backend/main.py` imports `app.main:app`.
> - A prior runtime check reported only 16 registered routes, apparently documentation/root routes, with the expected business endpoints absent. This conflicts with the current repository source. The exact deployed commit, active Gunicorn import target, Python module path, and live OpenAPI route list have not been reconciled in this audit.
> - **HIGH — do not treat repository router imports or CI as proof that production endpoints are registered.** Before any release, verify the running process command/import path and inspect `/openapi.json`/Swagger against the expected route inventory on the intended release. No server restart, AWS action or live endpoint change was performed here.


> **Authentication abuse protection review:**
> - **MEDIUM — no application-level login throttling/lockout found:** staff `POST /api/auth/login` and customer `POST /api/customer-auth/login` do not implement visible failed-attempt throttling, progressive delay or account lockout in the reviewed route/middleware. No rate-limit package is declared in `backend/requirements.txt`. Edge/WAF rate limiting may exist outside the repository but is NOT VERIFIED. Confirm protection for staff/customer login, customer registration, support-ticket intake and partner enquiries before public launch.


> **Storefront customer-account completeness review:**
> - **MEDIUM — My Orders is a placeholder despite customer sign-in:** the storefront account menu exposes “My Orders” but renders a placeholder and no customer-scoped order-history API is present. The UI copy says a secure customer identity is not yet available, although registration/login/session endpoints now exist. A customer-scoped order query should be bound to the authenticated customer identity, not a caller-supplied email.
> - **MEDIUM — addresses/profile are device-local only:** the address form explicitly saves PIN/address to browser localStorage and says it is not synced to the signed-in account. Customer account registration stores name/email/phone, but there is no persistent customer-address API/table in the reviewed implementation.
> - **LOW — security screen copy is stale:** it says customer authentication is not implemented, despite the existing register/login/session APIs; the actual unavailable functions are password change, verified contact changes and session management. Correct wording after the feature audit, without implying those security controls already exist.

> **Audit sequence agreed:** (1) finish the schema requirements/dependency audit, (2) audit all application modules and integrations against those requirements, (3) consolidate and prioritise findings in this register, and only then (4) prepare schema-change recommendations/change requests for Database Owner approval. No schema changes are being made at this stage.
>
> **Next required checks:** Complete table/column/constraint/index and application dependency mapping, then run the full application audit. After that, have the Database Owner run the read-only production checks in `docs/RELEASE_GATES.md` (database/version, full ledger and checksums, runner `--status` exit code, and backup storage). Record unavailable checks as NOT VERIFIED. No SQL, schema files, required-schema list, production database, merge, or deployment changed in this review.

---

This file is the concise, chronological change log for major Super Bajaar project updates. It complements `README.md`, which contains the detailed architecture, API contracts, workflows, setup and safety rules.

## How to maintain this log

- Add an entry for every major feature, API, database/schema, security, architecture, integration, deployment or workflow change.
- Keep each entry short: date, summary, impact, verification and PR/commit reference.
- Update this file in the same feature branch and pull request as the related change.
- Do not log secrets, tokens, passwords, private customer data or production connection strings.
- Routine formatting and minor non-functional fixes do not need entries.
- Record the actual status: proposed, implemented, CI-verified, merged or production-verified. Do not treat these as interchangeable.

---

## 2026-10-30 — Database migration safety and protected-main controls

**Status:** Merged to `main` in PR [#150](https://github.com/siinghniibandhan-wq/superbajaar/pull/150).

- Added a guarded database migration runner with dry-run/status/retry behaviour, migration checksum ledger, backup validation, per-file transactions and explicit failure codes.
- Added baseline protection for populated databases, least-privilege expectations and protection for historical migration filenames.
- Added PostgreSQL 15 and 16 CI matrix coverage and release-gate documentation.
- Enabled protected-main workflow requiring pull requests and the database matrix checks.

**Verification:** PR #150 CI passed its PostgreSQL 15/16 database checks and configured backend/frontend checks on the tested commit. These ran against disposable test databases. No production database migration, production backup validation or deployment was performed by those tests.

**References:** PR #150; merge commit `a693150d750182d91f4681259d655128f37f56db`.

## 2026-10-30 — README architecture, progress and API handbook

**Status:** Merged to `main` in PR [#151](https://github.com/siinghniibandhan-wq/superbajaar/pull/151).

- Added prominent GitHub Markdown caution, warning and important callouts for production safety, verification boundaries and documentation requirements.
- Added a project overview and evidence-based progress table separating CI results from production verification.
- Added overall infrastructure and request-flow diagrams, plus customer, admin and employee workflow diagrams.
- Expanded the API guide with authentication/public-route rules, route inventory, request lifecycle, HTTP error interpretation and debugging order.
- Documented current limitations, including no checkout stock reservation, no payment gateway charge/refund integration, no carrier integration and incomplete employee UI entry.

**Impact:** Future contributors have one source of truth for the architecture, role boundaries, API paths and known implementation gaps. Update the relevant README section whenever those contracts or workflows change.

**Verification:** Source files and route declarations were reviewed to prepare the documentation. The README update itself is documentation-only; production behaviour is not certified by this entry.

**References:** [PR #151](https://github.com/siinghniibandhan-wq/superbajaar/pull/151); latest README commit `178351f9ae1a697ba27a493cd608dd5af0c02c00` (branch `docs/readme-database-safety-20261030`).

## 2026-10-30 — Multi-category catalogue and storefront product details

**Status:** Implemented in PR #149; CI verification pending.

- Product create/edit supports assigning one product to multiple categories while retaining the legacy primary category field.
- Storefront category filters use assigned category IDs; product cards represent one parent product and product detail pages support variant selection and quantity before adding to basket.
- POS catalogue cards hide SKU while operational product/variant details retain it; POS layout styling is responsive.
- Reuses the existing `012_product_category_assignments.sql` schema; no duplicate migration was added.

**Verification:** Backend tests and both frontend production builds are being run in GitHub Actions. No production database migration or deployment is included.

## 2026-10-30 — Audited product deletion for owner/admin

**Status:** Implemented on a feature branch; CI and review pending.

- Added a Delete action for owner/admin catalogue users, with mandatory reason and confirmation.
- Backend enforces the role and writes a durable audit record in the same transaction as deletion.
- Products referenced by operational records are protected by database constraints; failed deletes roll back and direct users to Archive.
- Added additive migration `013_product_deletion_audit.sql` and marked it release-required.

**Verification:** Automated validation and CI pending. No production migration, database cleanup or deployment was performed.

## Ongoing documentation rule

For every future major change:
1. Update the relevant detailed section and diagrams in `README.md`.
2. Add a concise dated entry here in `IMPORTANT_UPDATES.md`.
3. Keep both changes in the same feature branch and PR as the implementation where practical.
4. Include only verified endpoints, status and test evidence.
5. Never push directly to `main`; use the protected pull-request process.
