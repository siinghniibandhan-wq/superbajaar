# HR & Payroll Completion — Design

**Design date:** 11 November 2026  
**Status:** Dated design record; implementation status is determined by current source, merged PRs and verified tests.  
**Related plan:** [HR & Payroll completion implementation plan](../plans/2026-11-11-hr-payroll-completion.md)

**Status:** Proposed implementation design  
**Branch:** `feature/hr-payroll-completion`  
**Scope:** Complete and harden the existing HR & Payroll workspace without replacing working workflows.

## Goals

1. Make the manager Overview an accurate operational and financial dashboard based on persisted records.
2. Make employee self-service views strictly employee-scoped.
3. Close material workflow gaps across workforce records, attendance, leave, expenses, payroll, statutory controls, accounting, onboarding/offboarding and portal access.
4. Improve mobile usability and accessibility without removing existing tabs, forms, actions or API contracts.
5. Prove behavior with focused backend/frontend tests and full CI.

## Existing implementation to preserve

The current `frontend/src/features/hr/HRWorkspace.jsx` already contains employee and department management, organisation chart, attendance, leave, expenses, salary revisions, variable earnings, payroll runs, payslips, statutory policy workspace and advanced lifecycle workflows. The backend `backend/app/api/hr.py` contains the corresponding API surface and uses authenticated user identity for employee self-service. Existing migration governance and the required schema list remain authoritative.

The implementation must be additive and compatibility-first. No existing endpoint, request/response contract, form, tab, state workflow, permission rule or payroll calculation is to be removed or silently changed.

## Proposed architecture

### 1. Dedicated overview aggregation API

Add a manager-facing endpoint under the existing HR router, recommended path `GET /hr/overview?month=YYYY-MM`, with a stable response divided into:

- workforce: total, active, inactive/terminated, joiners and exits for the selected period, department counts and headcount distribution;
- attendance: distinct employees present/absent/on leave/late, open sessions and a clearly defined attendance rate, for the selected date/month;
- leave and expenses: pending counts and amounts where the source data supports them;
- payroll: selected-period gross, employee deductions, employer contributions, net pay, run state, paid/linked state and outstanding exceptions;
- approvals: pending leave, expenses, salary revisions and variable earnings;
- controls: missing employee/profile data, statutory readiness and accounting posting exceptions;
- trends: month-by-month headcount, attendance and payroll aggregates only where historical source data supports the calculation.

Every metric must define its population, period, status filters, currency and null/empty semantics. Do not infer absence from missing punch records unless a valid assigned shift/calendar and holiday/leave context exists. If a metric cannot be computed reliably from available records, return an explicit unavailable state with a reason rather than a misleading zero.

Managers/admins receive organisation-wide aggregates. Employees must not be able to call this endpoint for organisation data; employee self-service continues to use employee-scoped endpoints and views.

### 2. Dashboard frontend

Refactor only the Overview rendering and its supporting styles into focused components if this reduces the current workspace's responsibility. Add:

- workforce KPI cards and department distribution;
- attendance summary and exception list;
- payroll financial summary and run lifecycle;
- approvals/action centre with links to existing tabs;
- compliance/accounting exception summary;
- historical trend views with selected-month context;
- loading, empty, partial-data, stale-data and API-error states.

Use existing design tokens and chart dependencies where present; do not introduce a new chart library without evidence it is needed. Preserve the month selector and refresh behavior. Mobile navigation must remain usable without hiding any existing tab.

### 3. Workflow completion audit

Verify and close gaps in these existing areas:

- employee onboarding, identity linkage, invitation and activation state;
- employee record validation, department/reporting hierarchy and status transitions;
- attendance shift assignment, holidays, late/early/absence rules, open sessions and auditable corrections;
- leave policies, accrual ledger, balance visibility, overlapping requests and cancellation/reversal;
- expense evidence, approval/rejection audit, reimbursement inclusion and duplicate prevention;
- salary revisions and variable earnings approval/effective-period rules;
- payroll period completeness, idempotency, recalculation controls, approval gates, payslip integrity and payment reconciliation;
- statutory policy snapshot/readiness, establishment/state-specific applicability and reconciliation outputs;
- accounting accrual posting, mapping exceptions, retry safety and payment voucher linkage;
- employee exit/final settlement and employee portal access lifecycle.

This is a verification scope, not permission to invent statutory rates or automatically file returns. Legal/statutory computations must use approved effective-dated policy data and remain reviewable by HR/CA. Gratuity, leave encashment and final settlement must not be represented as legally calculated when they are manager-entered approved amounts.

### 4. Security and data handling

- Enforce role checks on manager aggregates and all approval/action endpoints.
- Derive employee identity from the authenticated session, never client-supplied employee IDs.
- Avoid exposing salary, bank, tax identifier or personal documents to users without explicit authorization.
- Do not add plaintext bank/PAN/Aadhaar storage or enable bank export without encrypted storage, audited access and an agreed bank file specification.
- Keep portal invitation provisioning separate from employee record creation, with one-time expiring invitation tokens and ownership checks.
- Log sensitive workflow changes with actor, timestamp, reason and before/after state where the existing audit model supports it.

### 5. Database and migration policy

Prefer existing schema and records. Add a uniquely numbered additive migration only if repository evidence proves a missing persisted field/table is required. If needed, inspect all existing prefixes first, include the migration in `backend/schema_required.txt` when application code requires it, test it on disposable PostgreSQL, and leave production untouched absent explicit approval. Do not alter migration runner, timer, backup or deployment tooling.

## Completion criteria

- Overview metrics reconcile with source records for defined test fixtures and selected periods.
- Empty datasets, partial datasets, missing optional modules and API failures render honestly without fabricated values.
- Manager and employee authorization tests prove there is no cross-employee or cross-organisation data leakage.
- Existing HR forms, routes, tabs, API workflows and payroll approval controls remain functional.
- Attendance/leave/expense/payroll/accounting workflows have focused regression coverage, including boundary dates, duplicate submissions, reversals, rejected approvals, missing mappings and retry behavior.
- Responsive browser tests cover narrow mobile and desktop layouts; keyboard focus and accessible labels remain usable.
- Backend tests, frontend unit/contract/route tests, both frontend builds, database migration governance, security scans and browser quality checks pass on the PR head.
- No production migration, deployment, service restart or live data mutation is included in this work.

## Explicit boundaries

- No assumed statutory rates or legal eligibility decisions.
- No bank payment export or employee document vault until secure storage and access controls are designed.
- No production schema apply or deployment.
- No unrelated module, storefront, AWS or database automation changes.

## Recommended delivery order

1. Map existing HR endpoints, schema, permissions and tests; record gaps with evidence.
2. Define and test overview API metrics against existing schema.
3. Implement responsive dashboard and robust loading/empty/error states.
4. Close verified workflow/security defects in small, independently tested changes.
5. Run end-to-end regression and CI; open a reviewable PR with a precise completion matrix.
