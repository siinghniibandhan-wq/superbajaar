# HR & Payroll Completion Implementation Plan

**Plan date:** 11 November 2026  
**Status:** Dated execution plan; verify current code, PRs and tests before treating any checklist item as outstanding.  
**Related design:** [HR & Payroll completion design](../specs/2026-11-11-hr-payroll-completion-design.md)

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete and harden the existing Super Bajaar HR & Payroll workspace with reliable management analytics, secure employee self-service, and fully tested connected HR/payroll workflows.

**Architecture:** Preserve the existing FastAPI HR router, PostgreSQL schema, React workspace, and portal invitation foundation. Add a permission-checked aggregate overview endpoint using existing persisted data, render it as a responsive manager dashboard, then close only evidence-backed workflow gaps in independently testable slices. Existing payroll/statutory/accounting services remain the calculation and posting authorities.

**Tech Stack:** Python 3, FastAPI, Pydantic, psycopg/PostgreSQL, pytest, React 18, Vite, Node test runner, Playwright.

## Global Constraints

- Preserve existing employee forms and workflows, all existing HR tabs, API contracts, payroll calculation and approval logic, statutory policy controls, employee self-service, and portal invitation provisioning.
- Do not remove or silently change any existing endpoint, request/response contract, form, tab, state workflow, permission rule, or calculation.
- Manager/admin users receive organisation-wide aggregates. Employees remain restricted to their own data.
- Never infer absence from missing punch records without valid assigned shift/calendar and holiday/leave context.
- Return explicit unavailable state and reason when source data cannot support a metric; do not fabricate zeroes or estimates.
- Use approved effective-dated statutory policy data only. Do not invent statutory rates or automatically file returns.
- Do not add plaintext bank/PAN/Aadhaar storage or bank export without approved encrypted storage, audited access and bank file specification.
- Add only uniquely numbered additive schema migrations when proven necessary. Update `backend/schema_required.txt` in the same PR when code requires the migration. Do not alter migration runner, timer, backup or deployment tooling.
- Do not apply production migrations, deploy, restart services, or mutate live data.
- Keep storefront and unrelated admin modules untouched.
- Work on `feature/hr-payroll-completion`; open a PR to `main` after verification. Do not merge until explicitly instructed.

---

### Task 1: Establish HR baseline, metric contracts and authorization tests

**Files:**
- Modify: `backend/tests/test_hr.py`
- Create: `backend/tests/test_hr_overview.py`
- Inspect (no behavior change unless a failing test proves a defect): `backend/app/api/hr.py`
- Inspect: `backend/schema/020_hr_workforce_payroll.sql`
- Inspect: `backend/schema/022_hr_statutory_payroll_policies.sql`
- Inspect: `backend/schema/024_hr_payroll_accounting_accrual_link.sql`
- Inspect: `backend/schema/034_hr_scheduling_leave_lifecycle.sql`
- Inspect: `backend/schema/037_hr_salary_revision_history.sql`
- Inspect: `backend/schema/038_hr_variable_payroll_earnings.sql`
- Inspect: `backend/schema/039_hr_multi_establishment_payroll_accruals.sql`
- Inspect: `backend/schema/040_hr_final_settlement_earning_types.sql`
- Inspect: `backend/schema/041_portal_access_foundation.sql`

**Interfaces:**
- Consumes: existing `_actor(request)`, `_manager(request)`, `_hr_connection()`, and existing HR table schemas.
- Produces: explicit overview response contract and fixture-backed tests used by Task 2.

- [ ] **Step 1: Add failing metric and authorization tests**

Create tests for:
- manager-only overview endpoint returns 401 without a session and 403 for an authenticated non-manager;
- manager can request a valid `YYYY-MM` period and receives stable top-level sections `workforce`, `attendance`, `payroll`, `approvals`, `controls`, `trends`, and `data_quality`;
- employee cannot access organisation aggregates and existing `/attendance/me` and `/payroll/me/payslips` remain employee-scoped;
- invalid month and impossible date values return 422;
- empty source tables produce explicit zero counts only where zero is provable, while unsupported metrics carry `available: false` and a reason;
- attendance does not classify employees without published shift assignment as absent;
- date boundaries include the full selected calendar month and do not include adjacent-month records;
- payroll totals include only the selected period and documented eligible run states, with employee deductions separated from employer contributions.

Use isolated DB fixtures or the repository's established DB mocking pattern; never connect tests to production.

- [ ] **Step 2: Verify relevant failures**

Run: `cd backend && pytest -q tests/test_hr_overview.py`

Expected: tests fail because the overview endpoint and response contract do not exist yet; authorization and date-validation assertions identify the missing behavior.

- [ ] **Step 3: Map each metric to its authoritative table and state**

Document in test names/helpers the exact sources:
- workforce: `hr_employees`, `hr_departments`, joining and exit dates;
- attendance: `hr_attendance_sessions`, `hr_shift_assignments`, approved holiday calendars, approved leave and current employee status;
- payroll: `hr_payroll_runs`, `hr_payslips`, statutory snapshots/remittances and payroll accounting link tables;
- approvals: `hr_leave_requests`, `hr_expenses`, salary revision records and earning adjustments;
- lifecycle: `hr_employee_lifecycle_tasks`;
- compliance/accounting controls: approved policy versions, remittance statuses and payroll posting state.

Inspect actual column names and status constraints in migrations before writing SQL. Do not assume a table or column exists based only on a UI label.

- [ ] **Step 4: Verify baseline and contract tests**

Run: `cd backend && pytest -q tests/test_hr.py tests/test_hr_overview.py`

Expected: existing HR tests remain green; new contract tests pass after Task 2.

- [ ] **Step 5: Run backend integration checks**

Run: `cd backend && pytest -q`

Expected: complete backend test suite passes without production DB access.

- [ ] **Step 6: Commit the baseline test deliverable**

```bash
git add backend/tests/test_hr.py backend/tests/test_hr_overview.py
git commit -m "test(hr): define overview metric and access contracts"
```

---

### Task 2: Implement authoritative HR overview aggregation API

**Files:**
- Modify: `backend/app/api/hr.py` (register endpoint and request/response validation only)
- Create: `backend/app/services/hr_overview.py` (metric queries, period boundaries and aggregation)
- Test: `backend/tests/test_hr_overview.py`

**Interfaces:**
- Consumes: authenticated `Request`; query parameter `month: str` in `YYYY-MM`; existing HR PostgreSQL tables and Task 1 metric contract.
- Produces: `GET /api/hr/overview?month=YYYY-MM` manager-only JSON response:
  - `period: {month, start_date, end_date}`
  - `workforce: {total, active, inactive, joiners, exits, departments: []}`
  - `attendance: {available, reason, present, absent, late, on_leave, open_sessions, rate}`
  - `payroll: {available, reason, gross, employee_deductions, employer_contributions, net, run_status, run_count, accounting_status, exceptions: []}`
  - `approvals: {leave_count, expense_count, salary_revision_count, earning_count, lifecycle_overdue_count}`
  - `controls: {statutory_readiness, pending_remittances, accounting_exceptions, employee_data_issues}`
  - `trends: {headcount: [], attendance: [], payroll_cost: []}`
  - `data_quality: {partial, unavailable_metrics: []}`

- [ ] **Step 1: Add query/service tests for period-scoped aggregates**

Assert exact fixture values for active/inactive employees, joiners/exits, department totals, attendance categories, pending approvals, payroll totals and controls. Include employees with no shift, approved leave, holidays, open attendance sessions, multiple payroll runs, draft/unapproved runs, missing statutory policy and failed accounting posting.

- [ ] **Step 2: Verify focused failures**

Run: `cd backend && pytest -q tests/test_hr_overview.py`

Expected: failures identify the missing aggregation service and endpoint.

- [ ] **Step 3: Implement service queries and endpoint**

Implement parameterized SQL using half-open date ranges `[month_start, next_month_start)`. Use one consistent transaction/snapshot for the overview. Use aggregate queries rather than loading all employee, leave, expense and payroll records into Python. Add a bounded prior-period range for trend series.

Rules:
- Active/inactive classification must follow actual employee status values and documented date semantics.
- Joiners/exits are date-based and distinct from current active count.
- Present/late/open-session counts use distinct employee/session semantics and documented local timezone.
- Absence requires a published shift on a working day and exclusion of approved leave and holidays; otherwise report unavailable or not scheduled, not absent.
- Payroll totals must use persisted approved/finalized run/payslip records only; never add draft or superseded runs. Confirm the actual status model before query implementation.
- Net pay must reconcile to gross less employee deductions; employer contributions are displayed separately and never subtracted from employee net.
- Approval queues count only pending records.
- Missing policy or accounting mapping is a control exception, not a zero deduction or successful posting.
- Trend points with insufficient history are marked unavailable.
- Return currency as INR and amounts as decimal-safe numeric values serialized consistently.
- Never return individual salary or tax details in the organisation-wide aggregate.

Use `_manager(request)` before opening the aggregate query. Return 422 for invalid month and 503 for missing required HR schema using the existing HR connection error convention.

- [ ] **Step 4: Verify focused tests**

Run: `cd backend && pytest -q tests/test_hr_overview.py`

Expected: all metric, date-boundary, missing-data and role-isolation tests pass.

- [ ] **Step 5: Run HR regression and backend suite**

Run: `cd backend && pytest -q tests/test_hr.py tests/test_hr_overview.py`  
Run: `cd backend && pytest -q`

Expected: all HR tests and full backend suite pass.

- [ ] **Step 6: Commit the API deliverable**

```bash
git add backend/app/api/hr.py backend/app/services/hr_overview.py backend/tests/test_hr_overview.py
git commit -m "feat(hr): add permissioned workforce and payroll overview API"
```

---

### Task 3: Build responsive management Overview and preserve employee self-service

**Files:**
- Modify: `frontend/src/features/hr/HRWorkspace.jsx` (overview data loading and render integration)
- Modify: `frontend/src/features/hr/HRWorkspace.css` (remove only conflicting HR navigation/overview overrides and add scoped responsive styles)
- Create: `frontend/src/features/hr/HROverview.jsx` (dashboard sections and visualizations)
- Create: `frontend/src/features/hr/HROverview.css` (overview-only styles)
- Test: existing frontend unit/contract tests plus new `frontend/tests/unit/hr-overview.test.js` if compatible with current Node test conventions.

**Interfaces:**
- Consumes: `GET /hr/overview?month=YYYY-MM` from Task 2, existing `apiRequest`, manager role flag and existing selected month.
- Produces: manager-only `HROverview({data, loading, error, onNavigate, onRefresh})`; employee Overview remains scoped to existing self-service data and APIs.

- [ ] **Step 1: Add component tests**

Cover manager KPI rendering, INR formatting, empty datasets, partial/unavailable metrics, loading skeleton, retry action, API error, month change refresh, action links to existing tabs and employee view never rendering organisation payroll/headcount aggregates.

- [ ] **Step 2: Verify focused failures**

Run: `cd frontend && npm run test:unit`

Expected: new overview component tests fail before implementation while existing unit/contract tests continue to pass.

- [ ] **Step 3: Implement dashboard**

Render workforce, attendance, payroll, approvals, compliance/accounting controls and trend sections. Each section must show its own unavailable reason when data is not supported. Link action cards to existing tab identifiers without changing those tabs' behavior. Retain the existing month selector and Refresh button.

Keep manager-only API fetch separate from employee fetch. Do not request the manager endpoint for employee sessions. Ensure request cancellation/stale response protection when the month changes quickly. Preserve all existing state and API calls used by non-overview tabs.

- [ ] **Step 4: Improve mobile navigation and accessibility**

Use a compact horizontally scrollable tab bar with visible focus, active state, accessible labels and no clipped actions. At 320px, all tabs must remain reachable by scrolling; dashboard cards become one column on narrow screens and two columns where space permits. Tables remain horizontally scrollable. Respect reduced motion and color contrast.

- [ ] **Step 5: Verify focused frontend tests**

Run: `cd frontend && npm run test:unit`

Expected: HR overview tests and all existing unit/contract tests pass.

- [ ] **Step 6: Verify builds and route checks**

Run: `cd frontend && npm run build`  
Run: `cd frontend && npm run test:routes`

Expected: frontend build and admin route checks pass.

- [ ] **Step 7: Commit the dashboard deliverable**

```bash
git add frontend/src/features/hr/HRWorkspace.jsx frontend/src/features/hr/HRWorkspace.css frontend/src/features/hr/HROverview.jsx frontend/src/features/hr/HROverview.css frontend/tests/unit/hr-overview.test.js
git commit -m "feat(hr): deliver responsive workforce management overview"
```

---

### Task 4: Close verified HR workflow, payroll, statutory and accounting gaps

**Files:**
- Modify only evidence-backed sections of: `backend/app/api/hr.py`
- Modify only evidence-backed sections of: `backend/app/services/hr_statutory_payroll.py`
- Modify only evidence-backed sections of: `backend/app/services/accounting_posting.py`
- Modify only evidence-backed sections of: `frontend/src/features/hr/HRWorkspace.jsx`, `frontend/src/features/hr/HRAdvancedWorkflows.jsx`, `frontend/src/features/hr/HRStatutoryPolicies.jsx`
- Add focused tests under: `backend/tests/test_hr.py`, `backend/tests/test_hr_payroll_accounting.py`, and existing frontend test directories.
- Add a new uniquely numbered migration and update `backend/schema_required.txt` only if the audit proves a required persistence gap; determine next unused migration number by inspecting all schema filenames on the branch first.

**Interfaces:**
- Consumes: existing employee, attendance, leave, expense, salary revision, earning adjustment, payroll, statutory policy, remittance, lifecycle and accounting endpoints.
- Produces: unchanged public API contracts where possible; narrowly additive endpoints/fields only where a demonstrated workflow gap cannot be solved compatibly.

- [ ] **Step 1: Add regression tests for verified defects**

Audit current implementation against these cases and write a failing test only when the defect is reproducible:
- employee record with linked app user and invitation acceptance remains one-to-one and ownership-safe;
- onboarding/offboarding lifecycle task generation is idempotent and overdue tasks are visible;
- attendance adjustment records actor/reason and rejects invalid or overlapping shift/session data;
- leave balance ledger prevents duplicate accrual/consumption, cancellation reverses prior approved consumption exactly once, and overlapping requests are rejected;
- expense approval/rejection records actor/reason and approved reimbursement cannot be duplicated in payroll;
- salary revision approval rejects overlapping effective periods and only approved revisions affect the intended payroll period;
- variable earning approval is idempotent and cannot be included twice;
- payroll run calculation is idempotent for the same period, does not include terminated/ineligible employees incorrectly, preserves approved inputs, and blocks approval when required policy/mapping checks fail;
- payroll approval and payment transitions cannot be replayed to duplicate accounting entries;
- statutory remittance amount reconciles to employee plus employer portions and paid/filed transitions require their supporting references;
- accounting posting retry is safe after a timeout/partial failure and cannot create duplicate vouchers;
- final settlement amounts are explicit approved inputs and are not presented as legal calculations without approved policy evidence;
- employee portal invitation activation/revocation and termination access are synchronized without weakening token or supplier/employee ownership controls.

- [ ] **Step 2: Verify each focused failure**

Run the smallest relevant backend test file, for example: `cd backend && pytest -q tests/test_hr_payroll_accounting.py`.

Expected: only the specifically reproduced defect tests fail; existing tests remain unchanged.

- [ ] **Step 3: Implement minimal compatible corrections**

For every defect, retain existing endpoint and payload semantics. Add DB constraints only where they enforce an already-established invariant and can be safely deployed additively. Make multi-table transitions transactional. Use unique source references/idempotency constraints for ledger, payroll and accounting posting operations. Require a reason for rejected/overridden decisions and preserve actor audit. Do not guess Indian statutory thresholds/rates or tax outcomes; use approved effective-dated policies and report readiness gaps.

Do not add bank export, Aadhaar/PAN collection or document vault as part of this task unless a separate secure design is approved.

- [ ] **Step 4: Verify focused tests**

Run the exact affected test file(s) after each correction.

Expected: the new regression test passes and previously passing related tests remain green.

- [ ] **Step 5: Verify complete HR/backend regression**

Run: `cd backend && pytest -q tests/test_hr.py tests/test_hr_overview.py tests/test_hr_payroll_accounting.py`  
Run: `cd backend && pytest -q`

Expected: all tests pass. Any newly required schema file is included in `backend/schema_required.txt` and validated by schema governance CI; no production apply is performed.

- [ ] **Step 6: Commit each independently passing workflow correction**

```bash
git add [only the exact implementation and tests for the verified defect]
git commit -m "fix(hr): [specific corrected workflow]"
```

---

### Task 5: End-to-end verification, completion matrix and PR

**Files:**
- Modify: `docs/HR_PAYROLL_COMPLETION_STATUS.md`
- Test: backend HR/payroll suites, frontend unit/contract/route tests, browser quality tests and both frontend builds.
- PR: `feature/hr-payroll-completion` to `main`.

**Interfaces:**
- Consumes: completed API, dashboard and workflow behavior from Tasks 1–4.
- Produces: evidence-based completion matrix, PR with test evidence and explicit outstanding items.

- [ ] **Step 1: Add/extend browser regression coverage**

Test manager HR navigation, month selection, dashboard loading/error/empty states, all KPI sections, mobile horizontal tab access, employee self-service privacy, and navigation into existing HR forms without losing their existing functionality.

- [ ] **Step 2: Run full verification**

Run:
- `cd backend && pytest -q`
- `cd frontend && npm run test:unit`
- `cd frontend && npm run test:routes`
- `cd frontend && npm run build`
- `npm run build` at repository root to prove storefront remains unchanged and buildable
- the repository's existing Playwright/browser-quality workflow and all GitHub Actions required checks.

Expected: all tests, builds, security scans, migration governance and browser quality checks pass on the exact PR head SHA.

- [ ] **Step 3: Review diff and compatibility**

Confirm no storefront files, unrelated modules, database automation scripts, production env files or existing public HR contracts were changed. Confirm every migration number is unique and every required migration is listed exactly once.

- [ ] **Step 4: Write completion matrix**

For each HR area, label it complete, partially complete or blocked with linked tests/evidence. Record explicitly any statutory filing, bank integration or external service dependency that remains outside the approved scope.

- [ ] **Step 5: Open pull request**

Create a PR titled `Complete HR & Payroll management workspace`, base `main`, head `feature/hr-payroll-completion`. Include scope, migration details, compatibility notes, test commands/results and the completion matrix. Do not merge automatically.

- [ ] **Step 6: Final verification and handoff**

Re-fetch all workflow runs for the exact PR head SHA. Report only verified passing checks and actual remaining blockers. Do not claim production deployment or migration application.

## Unresolved external dependencies / decision seams

- Indian statutory applicability and effective policy values (PF, ESI, PT, TDS) must be supplied and approved by the employer's CA/payroll owner; engineering must not invent them.
- Bank payout export remains excluded until the bank format, maker-checker approval and secure handling requirements are supplied.
- Production schema application and deployment remain separately gated by explicit approval.
