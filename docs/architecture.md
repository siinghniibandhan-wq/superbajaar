# Architecture and API Contracts

> **Purpose:** Canonical technical description of the running application architecture, request/data flow, domain boundaries and API contracts. The README provides the short overview; this document owns the detailed technical reference.

## 1. Architecture principles

1. Keep one authoritative backend API and one persistent PostgreSQL data store.
2. Frontend pages call the shared API client; browser code never connects directly to PostgreSQL.
3. Backend handlers validate input, authenticate callers, enforce roles and apply server-side business rules.
4. Keep durable business records in PostgreSQL; use explicit transactions for multi-record operations.
5. Make retryable operations idempotent, especially payments, webhooks, orders, stock movements and synchronization.
6. Do not reset or destructively recreate production schema during application startup.
7. Document implemented behaviour separately from target architecture or planned modules.

## 2. Runtime topology

| Component | Current documented implementation | Responsibility |
|---|---|---|
| Customer storefront | React + Vite | Customer browsing and checkout UI |
| Admin / internal UI | React + Vite workspaces | Catalogue and operational administration |
| Frontend hosting | AWS Amplify | Build and serve frontend |
| API client | `frontend/src/services/api.js` | Base URL, `/api` prefix, auth headers, response/error handling |
| Reverse proxy | Nginx on existing AWS EC2 | HTTPS and upstream routing |
| Application server | Gunicorn + FastAPI | HTTP API runtime |
| Backend listener | `127.0.0.1:8001` | Internal backend listener |
| Database | PostgreSQL, `sb_app`, port `5432` | Persistent application data |
| Process operations | Existing systemd service/timer | Backend process and scheduled synchronization |
| CI | GitHub Actions | Backend tests, frontend builds and schema checks |

Do not change the established ports, services, hosting or API prefix without owner approval and a verified migration plan.

## 3. System context and request flow

```mermaid
flowchart LR
  C[Customer browser] --> STORE[React storefront]
  U[Owner / admin / staff browser] --> ADMIN[React workspaces]
  STORE --> CLIENT[Shared API client]
  ADMIN --> CLIENT
  CLIENT -->|HTTPS /api/*| NGINX[Nginx · EC2]
  NGINX -->|127.0.0.1:8001| APP[Gunicorn + FastAPI]
  APP --> AUTH[Authentication + role checks]
  AUTH --> ROUTERS[Domain API routers]
  ROUTERS --> DB[(PostgreSQL · sb_app :5432)]
  DB --> ROUTERS
  ROUTERS --> APP
  APP --> CLIENT
  CLIENT --> STORE
  CLIENT --> ADMIN
```

### Request lifecycle

```mermaid
sequenceDiagram
  participant UI as React UI
  participant Client as Shared API client
  participant Proxy as Nginx / Gunicorn
  participant API as FastAPI router
  participant Guard as Session / role guard
  participant DB as PostgreSQL
  UI->>Client: User action / api request
  Client->>Client: Configure base URL, /api prefix and token
  Client->>Proxy: HTTPS request
  Proxy->>API: Forward to 127.0.0.1:8001
  API->>Guard: Validate identity and permission
  Guard->>DB: Check active session / role as required
  DB-->>Guard: Session / role result
  Guard-->>API: Allow or reject
  API->>DB: Parameterised query / transaction
  DB-->>API: Result
  API-->>Client: JSON response or HTTP error
  Client-->>UI: Render result / error state
```

1. A page calls the shared API client.
2. The client applies the configured backend URL and single `/api` prefix, then attaches the correct token when required.
3. Nginx forwards the request to FastAPI through Gunicorn on port 8001.
4. Middleware/dependencies validate public-route exceptions, active sessions and roles.
5. The domain router validates the request, applies business rules and interacts with PostgreSQL.
6. The API returns a structured response; the frontend renders it.

The server, not the browser, is authoritative for price, tax, permissions, stock and order totals.

## 4. Source layout — actual implementation versus target pattern

### Current source map

- `frontend/src/main.jsx`: React entry.
- `frontend/src/app/`: application shell and routing.
- `frontend/src/pages/`: page/workspace entry points.
- `frontend/src/features/`: feature-specific UI and workflows.
- `frontend/src/components/`: reusable components.
- `frontend/src/layouts/`: shared layouts.
- `frontend/src/services/api.js`: shared API client.
- `backend/app/main.py`: FastAPI app, middleware and router registration.
- `backend/app/core/`: configuration and authentication infrastructure.
- `backend/app/api/`: HTTP route handlers.
- `backend/tests/`: backend tests.
- `backend/schema/`: versioned SQL migration files.
- `backend/scripts/apply_schema.sh`: schema migration runner.
- `backend/schema_required.txt`: release-required schema files.

Some current route handlers contain direct database access. A fully separated service/repository architecture is a design direction, not an assumption that every module already follows it. Do not restructure working modules solely to match an idealized folder diagram.

## 5. Domain boundaries

| Domain | Responsibility / data boundary |
|---|---|
| Identity and access | Staff/customer authentication, sessions, roles and permissions |
| Catalogue | Categories, products, attributes, variants and product images |
| Pricing | Variant prices, tax treatment and promotions |
| Inventory | Locations, balances, movements and adjustments |
| Purchasing | Suppliers, purchase orders and receiving |
| Orders | Checkout, order lifecycle and order summaries |
| Payments | Payment records and provider status; do not assume gateway capture/refund is implemented |
| Delivery | Shipment records, serviceability and delivery status |
| Customers / CRM | Customer records, support cases and related activity |
| Loyalty | Programme, referrals and points-related records |
| POS | In-person sales workflow |
| Accounting / tax | Double-entry ledger (`accounting_*` tables, migration 015): chart of accounts, vouchers and lines, GST invoices, reports, bank reconciliation, lock date and automatic posting from orders/payments/goods receipts. Reads operational tables; never writes them |
| HR / payroll | Employee and payroll operations; verify implementation before relying on scope |
| Reporting | Cross-domain read models and operational reporting |

Cross-domain workflows must preserve referential integrity and use explicit transactions where one business action changes multiple records.

## 6. API contract and access policy

All public API paths use the single `/api` prefix. Confirm the current route declaration and OpenAPI schema before implementing against a path; route inventories are maintained from source and can become stale.

### Route inventory

The current README/route inventory is a navigation aid. The authoritative contract for a particular endpoint is the current FastAPI route declaration and generated OpenAPI schema in the target environment. Before changing an endpoint:

1. Inspect `backend/app/main.py` and the relevant router.
2. Inspect request/response Pydantic schemas and authentication dependencies.
3. Confirm route and method in Swagger/OpenAPI.
4. Update this document with path, method, auth, role, request/response and error semantics.
5. Add or update backend tests and frontend API client usage.
6. Test the real UI → API → database behaviour where feasible.

### Accounting API (`/api/accounting`)

Source: `backend/app/api/accounting.py`; schema: `backend/schema/015_accounting_ledger.sql`; UI: `frontend/src/features/accounting/`.

**Authentication / authorization.** Staff bearer token with an active session (shared middleware). Reads: owner, admin, manager (router dependency `require_accounting_reader`, which runs after the session check). Writes (POST/PUT/PATCH): owner and admin only, enforced by the existing middleware write policy. Changing the books lock date: owner only. Other roles receive 403.

**Ledger rules (enforced in API and database).** Every voucher balances (deferred constraint triggers); each line is either debit or credit; posted amounts and accounts cannot be edited and vouchers/lines cannot be deleted (protect triggers) — corrections are reversal vouchers with a reason. Entries dated on or before `lock_date` are rejected. Voucher numbers are sequential per type and Indian financial year (`SI/2026-27/00001`). `idempotency_key` makes a retried POST return the original voucher (`idempotent_replay: true`). All amounts are server-calculated with `Decimal` and rounded half-up to paise.

| Method + path | Purpose | Request | Response / errors | Data effects |
|---|---|---|---|---|
| GET `/api/accounting/settings` | Business name, GSTIN, state code, default supply, lock date | — | settings row; 503 if migration 015 is missing | reads `accounting_settings` |
| PUT `/api/accounting/settings` | Update settings | `business_name`, `gstin` (15-char format), `state_code` (2 digits, must match GSTIN), `default_supply` intra/inter, `lock_date` | updated row; 403 lock date change by non-owner; 422 validation | updates `accounting_settings` |
| GET `/api/accounting/accounts` | Chart of accounts with balances | `include_inactive`, `as_of` | `items[]` (balance on natural side), `sub_types` | reads accounts + lines |
| POST `/api/accounting/accounts` | Create account | `code`, `name`, `account_type`, `sub_type`, `parent_id`, `description` | 201 account; 409 duplicate code; 422 invalid type/sub-type | inserts `accounting_accounts` |
| PATCH `/api/accounting/accounts/{id}` | Rename / describe / activate / deactivate | `name`, `description`, `is_active` | account; 409 system account deactivation; 404 | updates `accounting_accounts` |
| GET `/api/accounting/vouchers` | List / search vouchers | `voucher_type`, `from_date`, `to_date`, `search`, `limit` ≤500, `offset` | `items`, `total` | reads vouchers |
| GET `/api/accounting/vouchers/{id}` | Voucher with lines | — | voucher + `lines[]`; 404 | reads |
| POST `/api/accounting/vouchers` | Manual journal, receipt, payment, contra, expense, opening | `voucher_type`, `voucher_date`, `lines[]` (`account_id`, `debit`/`credit`, `narration`), party, reference, `due_date`, `idempotency_key` | 201 voucher; 422 unbalanced / type rule (receipt must debit cash/bank, payment must credit cash/bank, contra cash/bank only, expense must debit an expense account) / inactive account; 409 date on or before lock date | inserts voucher + lines |
| POST `/api/accounting/invoices` | Sales invoice, purchase bill, credit note, debit note with GST | `invoice_type`, `voucher_date`, `party_name`, `party_gstin`, `place_of_supply` intra (CGST+SGST) / inter (IGST), `settlement` credit/cash/bank/upi/card, `against_receipt` (purchase: clear 2050 GRNI instead of adding inventory), `round_off`, `lines[]` (`description`, `account_id`, `hsn_sac`, `quantity`, `rate` excl. GST, `discount`, `gst_rate`) | 201 voucher (`total_amount` = billed amount); 422 invalid GSTIN/HSN/rate/account; 409 locked date | inserts voucher + lines |
| POST `/api/accounting/vouchers/{id}/reverse` | Reverse a posted voucher | `reason` ≥5 chars, `reversal_date` | 201 reversal voucher; 409 already reversed, reversal of a reversal, or locked date; 422 date before original | inserts reversal; marks original `reversed` (status/audit columns only) |
| GET `/api/accounting/reports/trial-balance` | Trial balance | `as_of` | `items`, totals, `balanced` | reads |
| GET `/api/accounting/reports/profit-loss` | P&L | `from_date`, `to_date` (default: current financial year) | sections revenue/cogs/other_income/expenses, gross and net profit | reads |
| GET `/api/accounting/reports/balance-sheet` | Balance sheet incl. current-year earnings | `as_of` | assets, liabilities, equity, `balanced` | reads |
| GET `/api/accounting/reports/ledger/{id}` | Account ledger with running balance | `from_date`, `to_date`, `limit` | opening, items, closing (Dr positive) | reads |
| GET `/api/accounting/reports/day-book` | Day book with lines | `from_date`, `to_date`, `limit` | vouchers + lines | reads |
| GET `/api/accounting/reports/gst-summary` | Output vs input GST and rate-wise B2B/B2C summary | `from_date`, `to_date` | components, net payable, `by_rate`, disclaimer | reads |
| GET `/api/accounting/reports/parties` | Receivable or payable by party with 0–30/31–60/61–90/90+ aging | `kind` receivable/payable, `as_of` | `items`, `total` | reads |
| GET `/api/accounting/reports/summary` | Dashboard KPIs, monthly income/expense, recent vouchers | `from_date`, `to_date` | KPI fields, `monthly`, `recent` | reads |
| GET `/api/accounting/bank-reconciliation` | Book vs cleared balance for a bank/clearing account | `account_id`, `to_date`, `show` unreconciled/all | balances, `items`; 422 non-bank account | reads |
| PATCH `/api/accounting/lines/{line_id}/reconcile` | Mark/unmark a bank line as cleared | `reconciled_on` (null to clear), `bank_reference` | line; 422 non-bank line / date before voucher | updates `reconciled_on`, `bank_reference` only |
| GET `/api/accounting/sync/status` | Count operational records not yet posted | — | counts per source | reads orders, payments, inventory movements |
| POST `/api/accounting/sync` | Post pending orders (sales + COGS), cancellations (credit note), captured payments (receipt), refunds, goods receipts (Dr inventory, Cr GRNI) | `limit` ≤1000 | counts, `skipped_locked`, `errors[]`, `pending` | inserts vouchers; one savepoint per record; unique `(source_type, source_id)` makes reruns safe |

**Assumptions to review.** Order line totals are treated as GST-inclusive at each product's `tax_rate` with the default place of supply; order COGS uses current variant `cost_price`. Manual sales invoices do not relieve inventory/COGS (use a journal or the order sync for stock-backed sales). The GST summary is a bookkeeping aid, not a filed return.

**Verification.** `backend/tests/test_accounting.py` (unit) and `backend/tests/test_accounting_integration.py` (runs only with `SB_TEST_DATABASE_URL` pointing at a disposable database; refuses `sb_app` and AWS hosts).

### Authentication principles

- Public routes must be explicitly allow-listed.
- Authenticated requests require the correct bearer token and an active, non-revoked session where the route requires it.
- Staff and customer tokens are distinct; customer credentials must not grant access to staff resources.
- Roles are enforced on the backend. Hiding a UI control is not authorization.
- Owner/admin permissions must not be granted to another role merely to complete a workflow.
- Do not weaken middleware or public-route policy as a shortcut for a failing test.

### Contract change record

For each changed endpoint, record:

| Field | Required detail |
|---|---|
| Route | HTTP method + full `/api/...` path |
| Purpose | Business action and domain |
| Authentication | Public / staff / customer |
| Authorization | Required role or permission |
| Request | Path/query/body fields and validation |
| Response | Success schema and important fields |
| Errors | Expected 4xx/5xx and conditions |
| Data effects | Tables/entities read or changed |
| Verification | Swagger request, test and relevant end-to-end evidence |

## 7. Database and schema data flow

Application code reads/writes PostgreSQL through backend query/transaction logic. Schema changes are delivered separately through versioned SQL and the controlled migration runner.

```mermaid
flowchart TD
  APP[Backend application change] --> DEP[Does code require a new DB object?]
  DEP -->|No| APPTEST[Backend tests + API contract tests]
  DEP -->|Yes| MIG[One additive, idempotent numbered migration]
  MIG --> MANIFEST[Update schema_required.txt if release requires it]
  MANIFEST --> CI[Disposable PostgreSQL 15 + 16 CI]
  CI --> PR[PR review and owner merge]
  PR --> PREFLIGHT[Owner-only live ledger + checksum + backup preflight]
  PREFLIGHT --> RUN[Approved apply_schema.sh run]
  RUN --> LEDGER[schema_migrations / failures]
  LEDGER --> VERIFY[Health + feature verification]
```

The runner takes and validates a fresh backup before schema changes, runs each file in its own transaction, stores SHA-256 checksums and failure records, and uses `schema_required.txt` to decide whether a release may proceed. See `docs/DATABASE_CHANGE_RULES.md` for exact exit codes and failure semantics.

Never manually alter production schema to make an endpoint work. Verify the live ledger and database before making any production-state claim.

## 8. Known limitations and verification boundaries

These items must be checked against current code/tests before a release; they are not automatically proof of current defects:

- Order creation is not proof that stock was reserved or deducted; verify inventory transaction behaviour.
- Payment records/statuses are not proof of payment-provider capture, refund or webhook reconciliation; verify provider integration.
- Carrier/shipping status is not proof of live carrier integration; verify the actual connector and webhook path.
- Public checkout requires suitable edge-level rate limiting and bot protection before high-volume exposure.
- API health can indicate application/database readiness only to the extent the current health handler actually checks it.
- Route registration does not prove role correctness, database compatibility or complete frontend workflow.
- A CI pass on disposable databases does not prove production data, ledger, backup, deployed code or user journeys.

## 9. Architecture change control

An architectural change includes changes to hosting, runtime topology, ports, API prefix, authentication/session model, domain ownership, database boundaries, integration patterns, background jobs, deployment/synchronization or schema-release process.

Before implementation:

1. Read README, AGENTS and this document.
2. Describe current state, proposed state, reason, alternatives and migration/rollback impact.
3. Identify affected UI, API, backend, schema, integrations, CI and infrastructure.
4. Obtain owner approval for production-facing or protected architecture changes.
5. Implement in a focused branch and update this document and README in the same PR.
6. Add a dated decision/change record in `IMPORTANT_UPDATES.md`.
7. Verify with evidence at source, CI and target environment separately.

Do not silently convert a target design into a claim about the current implementation.
