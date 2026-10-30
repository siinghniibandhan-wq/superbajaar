# Project Progress Structure

This document is the standard work breakdown and progress-reporting structure for Super Bajaar. Every feature, module, bug, release and audit finding must be tracked under the relevant heading. Keep Development, Deployment and Audit separate: code completion is not deployment, and deployment is not audit approval.

## 1. Development

Track implementation work here. Split every task into Coding or Bug / Error Fixing.

### 1.1 Coding

#### 1.1.1 Frontend
- React application, pages, components, state, routing and client-side validation.
- Customer storefront, admin workspaces and employee workspaces.
- Responsive behaviour, accessibility and browser compatibility.

#### 1.1.2 Backend
- FastAPI services, business logic, validation, permissions and domain workflows.
- Database access, transactions, background jobs and integrations at the service layer.

#### 1.1.3 API
- Endpoint design and implementation, request/response contracts, schemas and versioning.
- Authentication/authorization contracts, status codes, pagination, error handling and API documentation.
- Frontend-to-backend contract compatibility.

#### 1.1.4 UI and Interface
- Layout, visual design, interaction patterns, forms, tables, navigation and feedback states.
- Design consistency, usability, loading/empty/error/success states and accessibility.

#### 1.1.5 Database and Schema (additional workstream)
- Data model, SQL migrations, indexes, constraints, triggers, permissions and migration compatibility.
- Follow repository database-change rules. Never modify protected or previously applied migrations; use only approved additive, idempotent migrations when required.

#### 1.1.6 Integrations and Automation (additional workstream)
- Payment, logistics, messaging, third-party services, webhooks, scheduled jobs and internal system integrations.

### 1.2 Bug / Error Fixing

Every defect must be classified by the layer where its cause exists. A symptom in one layer may originate in another; record both the observed symptom and confirmed root cause.

#### 1.2.1 Frontend
- Rendering failures, state defects, form behaviour, navigation, browser console errors and client-side validation.

#### 1.2.2 Backend
- Exceptions, business-rule defects, data handling, transaction failures, permissions and service/runtime errors.

#### 1.2.3 API
- Incorrect routes, request/response mismatches, status codes, authentication failures, validation errors and integration contract defects.

#### 1.2.4 UI and Interface
- Visual defects, alignment, responsive issues, broken interactions, unclear feedback and accessibility problems.

#### 1.2.5 Database and Schema (additional workstream)
- Query errors, incorrect constraints, migration defects, data integrity and schema/code mismatches.

#### 1.2.6 Integrations and Automation (additional workstream)
- Webhook failures, external API errors, sync failures, retries, duplicate processing and scheduled-task defects.

## 2. Deployment

Deployment is a separate release workstream. A change is not considered deployed merely because it is committed, merged or CI-tested.

1. **Pre-deployment readiness**
   - Scope and release owner confirmed.
   - Required reviews and CI checks passed.
   - Configuration, secrets references, dependencies and migration requirements reviewed.
   - Backup/rollback approach and impact assessed.
2. **Build and package**
   - Reproducible frontend/backend build and release artifact identified.
3. **Database release (only when required and approved)**
   - Migration reviewed, ordered, idempotent and compatible.
   - Target environment and migration ledger checked before execution.
4. **Application deployment**
   - Deploy through the approved existing pipeline and hosting arrangement.
   - Do not trigger production deployment without explicit authorization.
5. **Post-deployment verification**
   - Health checks, logs, critical API paths and relevant user journeys checked.
   - Verify UI → API → permissions/business rules → database → response.
6. **Release closure / rollback**
   - Record deployed commit, environment, time, verification evidence and outstanding issues.
   - Roll back only through the approved recovery plan if required.

## 3. Audit

Audit is an independent verification workstream. Findings must be evidence-based and must not be marked passed solely because code exists or CI is green.

### 3.1 Frontend
- Source and component quality, route coverage, state handling, form validation, browser behaviour and user journeys.
- Accessibility, responsive behaviour, performance and dependency risks.

### 3.2 Backend
- Business logic, validation, authorization, transaction boundaries, error handling, logging and data integrity.
- Runtime configuration, service health and operational behaviour.

### 3.3 API
- Route inventory, authentication, role/permission enforcement, request/response contracts, status codes and negative cases.
- Contract compatibility and end-to-end API-to-database behaviour.

### 3.4 UI
- Visual consistency, interaction correctness, navigation, responsive layouts, accessibility and loading/empty/error/success states.

### 3.5 Security
- Authentication, authorization, session handling, input validation, injection risks, CORS, CSRF where applicable, secrets handling, dependency vulnerabilities, rate limiting and sensitive-data exposure.
- Record severity, exploitability, evidence and remediation owner.

### 3.6 Others
- Database/schema integrity, migration safety, backup and recovery evidence.
- Integrations, webhooks, retries, observability, performance, reliability, documentation, compliance and operational readiness.
- Verify that production claims are supported by production evidence; CI against a disposable database is not production certification.

## 4. Quality Assurance and Testing (additional cross-cutting workstream)

Testing supports Development, Deployment and Audit; it does not replace any of them.

- Unit tests: isolated functions, components and business rules.
- Integration tests: service, API and database interactions.
- Contract tests: frontend/backend API compatibility.
- End-to-end tests: complete critical user journeys.
- Regression tests: previously working behaviour remains intact.
- Security, performance, accessibility and browser/device checks where applicable.
- Record exact command/workflow, commit SHA, environment, result and any skipped coverage.

## 5. Documentation and Release Records (additional cross-cutting workstream)

- Update the relevant README/API/schema/operations documentation with the implementation.
- Add a concise dated entry to `IMPORTANT_UPDATES.md` for major changes.
- Keep known limitations, decisions, risks, runbooks and rollback instructions current.
- Never include secrets, credentials or private customer data.

---

## Progress status vocabulary

Use one of these explicit states for each task. Do not combine them into a vague “done”.

| Status | Meaning |
|---|---|
| Not started | Work has not begun. |
| In progress | Work is actively being performed. |
| Blocked | Work cannot continue; state the dependency or decision needed. |
| Code complete | Implementation is written; verification may still be pending. |
| Fix complete | The identified defect has a proposed/implemented fix; regression verification may still be pending. |
| CI verified | The named automated checks passed on the exact commit. |
| Audit passed | The specified audit scope passed with recorded evidence. |
| Ready for deployment | Required code review, checks and release preparation are complete; deployment approval may still be required. |
| Deployed | The exact commit was released to the named environment. |
| Post-deployment verified | Named health checks and relevant end-to-end journeys passed in that environment. |
| Closed | Acceptance criteria met, evidence recorded and no unresolved blocker remains. |

A task can be code complete and still fail audit. A successful CI run does not mean deployed. A deployment does not mean post-deployment verified.

## Required progress report format

Use this structure for every module, feature batch or project status update:

```text
Project / Module:
Latest update:
Overall status:

1. Development
   1. Coding
      - Frontend:
      - Backend:
      - API:
      - UI and Interface:
      - Database and Schema:
      - Integrations and Automation:
   2. Bug / Error Fixing
      - Frontend:
      - Backend:
      - API:
      - UI and Interface:
      - Database and Schema:
      - Integrations and Automation:

2. Deployment
   - Readiness:
   - Build / release:
   - Database release (if applicable):
   - Deployment environment and commit:
   - Post-deployment verification:

3. Audit
   - Frontend:
   - Backend:
   - API:
   - UI:
   - Security:
   - Others:

4. Quality Assurance and Testing
   - Unit:
   - Integration / contract:
   - End-to-end / regression:
   - Exact CI run or command:

5. Documentation and Release Records
   - Updated documents:
   - Open risks / decisions:

Blockers:
Next actions:
Evidence / PR / commit:
```

### Reporting rules

- Put the **latest update, latest audit finding and critical blocker at the top** of the report.
- Show each status against its own workstream; do not hide incomplete work under a parent “completed” label.
- For every failed or blocked item, state the root cause, impact, owner/action and next step.
- For every passed item, attach verifiable evidence: PR, commit SHA, CI run, test output, audit result or deployment record.
- Distinguish repository/source verification, CI verification, staging verification and production verification.
- Never mark a task complete based only on assumptions, screenshots, route registration or code presence.
- Keep schema work separate from non-schema work and follow the repository's protected migration rules.
