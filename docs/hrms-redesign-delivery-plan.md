# Super Bajaar HRMS redesign and delivery plan

## Product objective
Deliver a complete, usable HRMS inside Super Bajaar. Super Bajaar remains the source of truth for employee identity, permissions, payroll, accounting and operational data. Prefer extending existing capabilities over duplicating them.

## UX acceptance principles
- Plain-language labels; group navigation by the employee lifecycle and daily work.
- Separate workspaces for employee records, attendance, leave, payroll, compliance and people development.
- Every screen has a clear page title, short explanation, primary action, useful filters, empty/loading/error states and a visible way back.
- Keep common actions reachable without forcing users through nested tabs.
- Responsive layouts: no clipped controls; tables scroll within their own container; touch targets remain comfortable on phones.
- Consistent forms with labels, examples, validation, confirmation for destructive actions and clear success/error feedback.
- Role-based navigation and server-side authorization; hiding a menu is not security.
- Accessible keyboard focus, semantic headings, readable contrast and status text that does not rely on colour alone.

## Existing capabilities to preserve and refactor
Employee and department records, organisation chart, attendance punching/register/corrections/audit, attendance policies and work locations, shifts and assignments, holiday calendars, leave applications/policies/balances/accruals/ledger, expense claims, payroll runs and approval/payment, salary revision approvals, variable earnings, payslips, statutory policies/profiles/remittances, establishment-based accounting accruals, employee self-service and onboarding/offboarding checklist templates/tasks.

## Target information architecture
1. HR Command Centre: overview, workforce metrics, pending actions and alerts.
2. Organisation: establishments, departments, designations and reporting structure.
3. Recruitment: requisitions, vacancies, candidates, interviews and offers.
4. Onboarding: joining tasks, document verification, induction and probation.
5. Employee Management: searchable directory, profile, employment history and documents.
6. Attendance & Workforce: register, shifts, rosters, locations, corrections and audit.
7. Leave Management: requests, policies, calendars, balances and ledger.
8. Payroll & Compensation: salary structures/revisions, payroll runs, earnings, deductions and payslips.
9. Benefits & Expenses: claims, reimbursements, allowances, advances and approvals.
10. Employee Self-Service: profile, attendance, leave, documents, payslips and requests.
11. Performance: goals, review cycles, appraisals and feedback.
12. Learning & Development: training, enrolments, skills and certifications.
13. Assets & Equipment: asset register, assignment, return and maintenance.
14. Travel: requests, approval and expense settlement.
15. Separation & Exit: resignation, notice, clearance and final settlement.
16. Documents & Policies: document library, acknowledgements and expiry tracking.
17. Compliance: establishment records, statutory policies and remittance reconciliation.
18. Reports & Analytics: workforce, attendance, leave, payroll and recruitment reporting.
19. Approvals: central inbox, history and delegation, backed by existing approval APIs.
20. HR Settings: role/permission, workflow and policy configuration.

## Delivery phases and definition of done

### Phase 1 — Usability foundation
- Replace cramped, horizontally scrolling HR tabs with grouped, labelled, responsive navigation.
- Clarify names and descriptions without changing API contracts.
- Validate desktop, tablet and phone layouts, keyboard navigation and existing manager/employee access.
- Run frontend unit/contract tests and production build.

### Phase 2 — Core HR workspaces
- Extract employee directory/profile and organisation management from the large workspace.
- Separate attendance, leave and workforce planning into independent pages.
- Preserve all existing endpoints, forms, filters, approvals, audit history and exports.
- Add component and workflow tests.

### Phase 3 — Payroll and compliance
- Separate payroll, salary history, variable earnings, payslips, expenses and statutory administration.
- Preserve full-month payroll rules, approval controls, establishment-specific accruals and accounting mappings.
- Make statutory reconciliation limitations explicit; do not imply CSV export is portal filing.

### Phase 4 — Employee lifecycle
- Build recruitment and candidate pipeline.
- Expand onboarding/offboarding checklist engine into joining, probation and exit workflows.
- Add document handling only with appropriate access, audit and retention controls.

### Phase 5 — People development and operations
- Implement performance, training, assets and travel only after data model and workflow requirements are verified.
- Avoid creating placeholder screens that look operational but have no working API.

### Phase 6 — Administration, reports and hardening
- Consolidate approvals and reporting where backend support exists.
- Add missing APIs and migrations only after schema review and backward-compatibility checks.
- Complete role-matrix, accessibility, responsive, security and regression testing.

## Known gaps to verify/build
Recruitment, full performance/appraisal, training, asset allocation, travel, document upload/library, formal resignation/exit workflow, central approvals inbox, and dedicated HR analytics are not established as complete standalone workflows by the inspected HR route set. Treat each as a product capability requiring design, API/schema work and tests—not merely a navigation link.

## Current implementation slice
- Grouped, responsive HR navigation with clear labels and touch-friendly controls.
- Employee directory search, department/status filters, reset and empty states.
- Dedicated Employees and Departments views within People Management.
- Employee profile summary with reporting line, contact details, employment dates, compensation snapshot, edit and salary-history actions.
- Leave application and review workspace with combined search/status/type filters.
- Onboarding/offboarding task dashboard with workload counters, overdue tracking, task search/status filters, assignment, start, completion, waiver and reopen actions.
- Lifecycle templates support descriptions, owner roles, due-date offsets, sequence and required-task flags.
- Lifecycle task event history is visible from the task list, backed by the existing permission-checked audit endpoint.
- Reusable lifecycle filter/summary helpers have focused frontend unit tests.
- Employee date handling now safely accommodates legacy records with a missing joining date.
- No new backend tables, API contracts or permissions were introduced in this implementation slice.

## Employee records slice delivered
- Emergency contacts: create and list active/inactive contacts, optional primary contact, phone/email/address fields, soft deactivation and actor/timestamp audit events.
- Previous employment: capture employer, job title, employment type, location, date range and notes; records are append-only so corrections are additive rather than destructive.
- HR manager-only API authorization; no employee ID is accepted from client payloads as an authority source.
- Employee profile UI includes contact management, prior-employment history and record audit history.
- Migration `070_hr_employee_records.sql` is included in `backend/schema_required.txt`; it has not been applied to production.
- Focused backend validation and authorization tests added.

## Remaining work — do not mark HRMS complete yet
- Split the monolithic HR workspace into independently testable employee, attendance, leave, payroll and compliance workspaces.
- Secure employee documents remain blocked pending a verified storage, access and retention design. Emergency contacts and prior employment history are now implemented as manager-authorized employee-profile records with validation and append-only audit events.
- Recruitment, performance, learning, asset management, travel, central approvals and dedicated analytics remain separate capability projects.
- Add workflow-level tests and complete manual role-matrix, keyboard, phone/tablet/desktop and regression QA.
- Confirm production migrations and deployment compatibility before any release.

## Release gates
- No broken existing employee/manager workflows.
- No permission escalation or client-only security.
- No destructive schema changes.
- Tests pass and production build succeeds.
- Manual QA at narrow phone, tablet and desktop widths.
- Each delivered module has real data/actions, loading/empty/error states and accessible navigation.

## Integrated enterprise HR workflows — implementation in progress

The feature branch now contains an additive enterprise workflow foundation for recruitment, employee documents, performance, learning, assets, travel, exit and analytics. It includes domain-specific record types, controlled status transitions, optimistic version checks, append-only audit events, employee self-service scoping, manager-only master-record controls and an HR workspace entry point.

Employee document files use the private document bucket, server-side AES256 encryption, employee-scoped object keys, PDF/JPEG/PNG signature checks, a 10 MB upload limit, SHA-256 metadata and short-lived access-checked download links. The document metadata endpoint cannot be used to inject arbitrary object keys; uploads must pass through the private storage service.

This is not yet a completion claim for the eight domains. Remaining end-to-end work includes dedicated domain screens and field validation, recruitment interview/offer/hiring integrations, document malware scanning/retention/expiry policies, performance cycle and calibration workflows, course catalogue/progress/certification, asset procurement/stock and custody reconciliation, travel booking/advance/claim settlement integrations, full-and-final exit calculations and clearance gates, and computed analytics/report exports. The new migration must be applied in a controlled environment; CI, DB integration, browser QA, S3 configuration/permissions, retention and security review are release gates.


## Latest enterprise workflow integration progress

The enterprise workflow slice has advanced beyond generic record entry:

- Recruitment offer conversion now creates the HR employee, opening salary version and permanent employee identity in the same database transaction, links an optional staff login, and generates tasks from the active global onboarding template when configured. Offer/application/candidate records and their audit events are updated together.
- Employee document upload enters a pending HR-review state. Managers move it through review and verification; employees can download only verified files. Expiry dates are persisted in the shared due-date column.
- Performance supports employee self-review records with bounded ratings, in addition to manager review cycles, reviews, goals and feedback.
- Learning enrollment requires a published/enrolled course; certificates require a completed enrollment and a passing assessment. Certificate validity is stored as a due date.
- Asset allocation is linked to an employee profile. Assignment synchronizes the asset master state; employees can acknowledge custody; return, maintenance and write-off synchronize the master asset and append audit events.
- Travel claims require completed travel and a receipt reference, create a linked record in the existing HR expense workflow, and cannot be marked reimbursed until that expense has been approved and paid through payroll.
- Exit completion is gated on department clearances and a completed full-and-final settlement record. Completion updates the employee's termination status and exit date and disables the linked staff login using the existing HR identity convention.
- The analytics page consumes the existing permission-checked HR overview aggregation. It deliberately displays unavailable attendance measures as unavailable instead of inferring absence or lateness.
- Migration 072 adds unique candidate-email, asset-tag, candidate/job application, and document-object-key indexes plus a due-date lookup index.

Latest validated branch head at this update: `922c81b2f6cb8f3bc628a278de69d13377ca16b4`. Backend identity tests passed (664 passed, 62 skipped, 1 warning); frontend tests and production build passed; Python dependency/SAST, frontend dependency audit and secret scanning passed.

## Still not production-complete

The eight domains still need malware scanning and retention/expiry automation for documents; candidate communication and offer letter signing; configurable performance templates, weighting and calibration; richer learning evidence/provider integrations; procurement, warranty and physical stock reconciliation for assets; travel policy/booking/finance integrations; statutory notice, leave/loan deductions and accounting-backed final settlement; and enterprise analytics filters, exports and scheduled delivery. PostgreSQL migrations 070–072 have not been applied to production. Live database integration, S3/IAM configuration, malware-scanner integration, manual responsive browser QA and release/deployment checks remain release gates.


## Additional workflow details at validated head 922c81b

- Performance review templates are versioned records with JSON section validation and rating-scale bounds. Review cycles are linked to employee goals and self-reviews; manager appraisals require an active template and the correct cycle stage; calibration and employee acknowledgement records are separately permissioned.
- Employees can select only published learning courses and active travel policies from linked-record selectors. Learning progress evidence is scoped to the enrolled employee and a valid in-progress enrollment.
- Travel policies define eligible employment types, trip caps, currency and per-diem ceilings. Booking, advance and claim amounts are checked against the selected policy; claims create existing HR expense records and flow through approval and paid-payroll status before the travel request is marked reimbursed.
- The manager expiry queue surfaces employee documents, learning certificates and asset warranties that are due within the next 30 days or already overdue.
- Asset master records retain vendor, purchase date, purchase reference, location and warranty expiry metadata. The warranty date is included in the shared due-date index.
- The analytics workspace provides a CSV export of the existing HR overview metrics; richer filters and XLSX/PDF export remain outstanding.
