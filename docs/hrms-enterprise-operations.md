# HR enterprise operations

This guide covers the seven non-recruitment HR domains in the HR enterprise workspace. Recruitment remains separate.

## Required document-storage controls

Employee document uploads require all of the following:

- `SB_PRIVATE_DOCUMENT_BUCKET`: private S3 bucket name.
- `SB_S3_REGION` or `AWS_REGION`: bucket region.
- `SB_DOCUMENT_CLAMAV_HOST`: reachable ClamAV daemon host.
- Optional `SB_DOCUMENT_CLAMAV_PORT` (default `3310`).
- Optional `SB_DOCUMENT_CLAMAV_TIMEOUT_SECONDS` (default `10`, maximum `60`).

A loopback-only ClamAV service definition is provided at `deploy/hrms/clamav.compose.yml`. Start it with `docker compose -f deploy/hrms/clamav.compose.yml up -d`, then set `SB_DOCUMENT_CLAMAV_HOST=127.0.0.1` and `SB_DOCUMENT_CLAMAV_PORT=3310` in the backend service environment. The first signature database download can take several minutes. Verify service health before enabling document uploads.

Run `bash deploy/hrms/s3-bucket-security-check.sh` with an AWS identity that can inspect the bucket. It fails unless all S3 public-access blocks are enabled, default encryption is AES256, versioning is enabled and the bucket policy is not public.

Uploads are blocked when the malware scanner is missing or unavailable. Files are checked by ClamAV before private S3 storage, and verification is blocked unless the stored scan result is clean. Downloads remain short-lived, employee-scoped and encryption-checked.

Set a document expiry date separately from its retention deletion date. HR can place a legal hold by setting `payload.legal_hold=true` on the document record. Expiry reminders for documents, learning certificates and asset warranties are stored as employee-scoped in-app notifications. An authorised HR manager can refresh the reminder queue with `POST /hr/enterprise/notifications/refresh`; employees can view and acknowledge their own reminders through `GET /hr/enterprise/notifications` and `POST /hr/enterprise/notifications/{id}/read`. An external scheduler can invoke the refresh endpoint daily.

After a document has been archived and its retention date has passed, an authorised HR manager can invoke:

`POST /hr/enterprise/documents/retention/execute`

This deletes the private S3 object and records an immutable audit event. The endpoint is designed to be invoked by an approved scheduler; no scheduler or email delivery service is configured by this feature branch.

## Domain workflows

### Performance management

- Create an active review template and a review cycle.
- Add weighted goals to the cycle. Active goal weights cannot exceed 100%.
- A cycle cannot be activated until its goals total exactly 100%.
- Goal edits re-check the total under a cycle row lock.
- Self-review, manager review, calibration and acknowledgement remain role-separated workflow actions.

### Learning and development

- Publish a course before creating enrollments.
- Employees record progress evidence against their own enrollment.
- Assessment attempts are limited by the course's `max_attempts` (1–20); the default is three.
- Certificates require a completed enrollment and at least one passing assessment.
- Certificate validity dates feed the expiry queue.

### Asset management

- Create a procurement request with item lines containing `description`, `quantity` and `unit_cost`.
- Approve procurement before receiving stock.
- Stock receipts must match ordered item descriptions and cannot exceed the ordered quantities. Procurement status moves from approved to partially received or received.
- Record physical reconciliations with a reason for any variance.
- Asset loss records support an investigation lifecycle.
- Asset register entries can calculate straight-line or reducing-balance depreciation from purchase value, salvage value, useful life and the selected as-of date.

### Travel and expenses

- Travel policies can constrain employment type and employee job grade.
- A policy grade of `all` applies to every grade; otherwise it must match the employee's `job_grade`.
- Requests are checked against trip and per-diem limits.
- Bookings and advances are checked against the approved request and policy caps.
- Claims create records in the existing HR expense approval and payroll reimbursement workflow. A claim cannot be marked reimbursed until the linked expense is reimbursed.

### Resignation and exit

- Exit cases require a linked employee and a future last working date.
- Department clearance records must be completed before case closure.
- Full-and-final settlement amounts must reconcile: net due = gross due − deductions.
- A positive net settlement creates a pending `final_settlement` payroll earning adjustment for the payable month. It must pass the existing independent-review and payroll approval/payment controls before the settlement can be completed.
- No jurisdiction-specific gratuity, leave-encashment or notice-pay formula is silently assumed; the approved component amounts must be supplied from the applicable policy and payroll calculation.

### HR analytics

The enterprise analytics endpoint supports date, domain, record-type, status and department filters:

`GET /hr/enterprise/analytics/enterprise?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD`

The workspace includes CSV, XLSX and PDF exports. Scheduled workspace snapshots can be generated by `POST /hr/enterprise/analytics/scheduled/run`; an external scheduler must invoke this manager-protected runner. Email delivery is not configured by this branch.

## Database rollout

The feature branch adds migrations 071–074 for enterprise workflow records, integrity indexes, employee job grades and durable expiry notifications. They are additive and must be reviewed and applied in the target environment through the repository's normal controlled migration process. They have not been applied to production by this work.

## Release checks still required

- Configure and verify the private S3 bucket, IAM policy, encryption, backup and ClamAV service.
- Configure an external scheduler to invoke document-retention execution and any approved reminder/report jobs.
- Run migrations against a staging database and verify payroll, leave, identity and accounting integrations.
- Complete manual browser QA at phone, tablet and desktop widths.


## Staging browser QA

The frontend has Playwright configured. After staging is deployed with migrations applied and HR test users/data configured, run:

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
```

The current Playwright config starts a local production preview. Run the suite against staging only with a dedicated staging Playwright config that disables the local webServer and sets `baseURL` to the staging host. Cover manager and employee roles, all seven domain tabs, mobile width (390px), tablet width (768px), desktop width (1440px), upload/scanning failure, booking provider failure/retry, advance voucher idempotency, exit policy approval, leave/loan calculations, report exports and retention legal holds. Capture screenshots and traces for failures. This branch does not have access to the target staging host or seeded test identities, so live staging browser QA remains an environment execution gate.


## Employee loan accounting configuration

Employee loans are created as drafts, approved by a different manager, and only become active when the approved principal is disbursed. Disbursement posts a balanced payment voucher: debit employee-loan receivable and credit the configured bank/cash account. Repayments post a receipt voucher: debit bank/cash and credit employee-loan receivable.

- `SB_EMPLOYEE_LOAN_RECEIVABLE_ACCOUNT_CODE`: defaults to `1150` (Employee loans receivable, added by migration 079).
- `SB_EMPLOYEE_LOAN_BANK_ACCOUNT_CODE`: defaults to `1010`; set this to the actual funding bank or cash ledger account.
- Apply `079_hr_employee_loan_accounting.sql` after migrations 070–078 before enabling the loan disbursement action.

Travel booking and payout require provider credentials and endpoints:
- `SB_TRAVEL_BOOKING_API_URL`, `SB_TRAVEL_BOOKING_API_TOKEN`, `SB_TRAVEL_BOOKING_PROVIDER`.
- `SB_TRAVEL_PAYOUT_API_URL`, `SB_TRAVEL_PAYOUT_API_TOKEN`, `SB_TRAVEL_PAYOUT_PROVIDER`.
- `SB_TRAVEL_ADVANCE_ACCOUNT_CODE` and `SB_TRAVEL_BANK_ACCOUNT_CODE` for the accounting voucher.

Do not enable live disbursement in production until the provider has been tested with a controlled low-value transaction and the bank/ledger account mappings have been confirmed by Finance.
