# Super Bajaar Unified Identity System — Phase 1 Audit

**Audit baseline:** `main` at `ef1de4682e8416edfd0db7d63ee3ecc7bab7bf41`  
**Audit date:** 11 November 2026  
**Scope:** Repository source, schema migrations, API and test coverage  
**Production status:** Not inspected or changed. No live database query, migration, deployment, service restart or AWS change was performed.

> **Historical audit snapshot — superseded for current implementation status.** This document records the Phase 1 baseline before implementation. The Unified Identity System has since been implemented incrementally and merged through PRs #54, #55, #57 and #58. For current capabilities, limitations and rollout status, use [the implementation guide](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md). The original findings below are preserved as the historical audit record.

## Executive conclusion

The repository has separate identity and access paths for customer accounts, staff/admin users, employee records and vendor portal access. There is useful existing functionality to preserve, but no unified master identity/SBID register or central identity-resolution service.

At the 11 November 2026 audit baseline, the feature was **not implemented yet**. This statement is historical and must not be used as the current status; see the implementation guide linked above. Existing links are relationship-specific and must not be mistaken for a unified identity model:

- Customer storefront login is held in `customer_accounts`.
- Staff/admin login is held in `app_users`.
- HR workforce records are held in `hr_employees`; `hr_employees.user_id` optionally links an employee record to an `app_users` row.
- Vendor portal access is held in `vendor_portal_users`; it links an `app_users` row to a `suppliers` row.
- CRM customer-account linking uses `customer_account_customer_links`; this links a storefront customer account to a CRM customer record, not to an employee/vendor/person master.
- Loyalty accounts are currently addressed by customer email; referral ownership is tied to customer-account IDs.

A complete implementation needs an additive identity layer and a staged compatibility migration. Replacing the existing authentication systems in one step would create unnecessary risk.

## 1. Existing architecture and findings

### 1.1 Customer identity and authentication

Files reviewed:
- `backend/app/api/customer_auth.py`
- `backend/schema/010_customer_accounts_referrals.sql`
- `backend/schema/011_customer_phone_uniqueness.sql`
- `backend/tests/test_customer_auth.py`

Findings:
- Customer registration creates a row in `customer_accounts` and customer login/session tokens are separate from staff/admin login.
- Email is normalised to lowercase. Indian mobile variants are canonicalised in application validation and a unique expression index protects canonical phone uniqueness.
- Registration checks existing customer accounts and selected legacy customer/order/loyalty contact fields, then rejects a match with HTTP 409.
- It does not resolve a customer against an employee or vendor, create an SBID, or offer a verified identity-link flow.
- Referral code is generated on the customer account. `customer_referrals` refers to customer-account IDs; this is not a platform-wide referral identity.
- The current duplicate response is a hard rejection rather than a safe account-recovery/identity-claim process.
- Existing customer sessions reference `customer_accounts`; this relationship must remain valid during rollout.

### 1.2 Employee identity and authentication

Files reviewed:
- `backend/app/api/auth.py`
- `backend/app/api/portal_invitations.py`
- `backend/app/api/employee_portal.py`
- `backend/schema/020_hr_workforce_payroll.sql`
- `backend/tests/test_auth.py`
- `backend/tests/test_portal_workflows.py`

Findings:
- `app_users` is the staff/admin authentication account table. Its role values are access/permission roles, not person profile types.
- `hr_employees` is the employee/workforce profile. It has its own unique `employee_code`, unique email, and nullable unique `user_id` reference to `app_users`.
- Employee portal invitations can create/link an `app_users` record to an existing HR employee.
- An employee record created outside that invitation flow may remain unlinked (`user_id IS NULL`).
- The numeric `app_users.id` is an internal authentication key, not an Employee ID and not a permanent cross-platform identity.
- Employee exit/status changes must not delete the employee profile, payroll history or underlying login/audit references.

### 1.3 Vendor identity and authentication

Files reviewed:
- `backend/app/api/portal_invitations.py`
- `backend/app/api/vendor_portal.py`
- `backend/schema/041_portal_access_foundation.sql`
- `backend/tests/test_portal_invitation_service.py`
- `backend/tests/test_portal_workflows.py`

Findings:
- Vendor/business master records are represented by `suppliers` (retain this database/API contract for compatibility).
- Vendor portal login is represented by `app_users` plus `vendor_portal_users(user_id,supplier_id)`.
- The invitation workflow provisions access to an existing supplier record; it does not create a master identity for the vendor organisation or its representatives.
- The schema permits multiple user/supplier relationships, but it does not define a person-to-organisation identity relationship or SBID.
- A vendor organisation and its authorised human representatives need distinct identities and explicit authority links. A vendor login must not automatically imply ownership of the organisation identity.

### 1.4 CRM customer links

Files reviewed:
- `backend/app/api/customers.py`
- `backend/tests/test_customers.py`
- `backend/tests/test_customers_crm.py`

Findings:
- The CRM linking workflow links a storefront `customer_accounts` row to a CRM `customers` row.
- It records a verification method, timestamp, actor and link timestamp.
- This is a useful precedent for auditable linking, but it does not link customer, employee and vendor identities into one master record.
- Existing CRM customer IDs and their order/support relationships must remain unchanged.

### 1.5 Loyalty and referral

Files reviewed:
- `backend/app/api/loyalty.py`
- `backend/app/api/customer_auth.py`
- `backend/schema/001_loyalty_programme.sql`
- `backend/schema/010_customer_accounts_referrals.sql`
- Loyalty API and integration tests.

Findings:
- Loyalty account lookup is currently based on `customer_email`; card number is stored on the loyalty account.
- Loyalty transactions reference the loyalty account. These ledger rows and balances must remain immutable and reconcilable.
- Referral codes are created on customer accounts; referral tracking references customer-account IDs.
- The customer schema explicitly separates referral tracking from reward issuance. That separation must be preserved: no reward may be issued merely because a person is an employee or vendor.
- The SBID integration should add stable references, not re-key or rewrite the historical ledger in-place.

### 1.6 Permissions and identity types

Files reviewed:
- `backend/app/api/auth.py`
- `backend/schema/036_configurable_rbac.sql`

Findings:
- The current role system contains `super_admin`, `admin`, `manager`, `staff`, and `viewer`; these represent permissions/authority.
- User-specific module permissions are separate from the login account role.
- Do not add Vendor, Customer or Employee as privileged roles. Profile types and permission roles must remain separate concepts.
- One SBID may have multiple profiles and multiple permission assignments, with scope restrictions and auditable grants.

## 2. Current-state coverage matrix

| Capability | Current state | Audit result |
|---|---|---|
| Customer account and login | Separate customer auth | Exists; not unified |
| Customer duplicate email/mobile checks | Customer/legacy checks | Partial; no cross-profile resolution |
| Employee profile and employee code | HR employee table | Exists; no SBID |
| Employee login link | Invitation or manual link | Partial; no central resolver |
| Vendor master and portal access | Supplier + portal relationship | Exists; no organisation/person SBID |
| CRM customer-account link | Audited account-to-CRM link | Exists; narrower than identity |
| Multiple verified contact points per person | No shared identity contact registry | Missing |
| Permanent SBID | No master identity table/service found | Missing |
| Customer/Employee/Vendor IDs on one register | No central register | Missing |
| Organisation identity and representative links | No unified model found | Missing |
| Safe identity match/claim popup | No cross-profile claim workflow found | Missing |
| Verified linking across all profile types | No central linking workflow found | Missing |
| Identity merge/split with audit | No unified workflow found | Missing |
| Loyalty card linked to SBID | Email-based lookup | Missing |
| Referral code/link linked to SBID | Customer-account-based | Missing |
| Central identity audit history | No unified identity event log found | Missing |
| Identity administration workspace | No unified register found | Missing |

## 3. Target architecture

The target model is an additive identity layer. Existing profile tables remain authoritative for their domain data; the identity layer becomes authoritative for cross-domain identity relationships.

### 3.1 Core entities

1. **`identity_parties`** — one permanent master identity per individual or organisation; immutable generated SBID; party type; lifecycle status; created/updated timestamps.
2. **`identity_contacts`** — one row per email/phone/contact point; normalised value, type, verification state/time, primary flag, validity dates and source. Enforce uniqueness for active verified identifiers only where policy allows; shared/recycled contacts must be representable without silently equating people.
3. **`identity_profiles`** — typed, unique links from an SBID to existing domain records (customer account, CRM customer, employee, supplier/vendor organisation, future profile types). Use typed source keys and explicit uniqueness constraints.
4. **`identity_relationships`** — explicit person-to-organisation relationships (representative, owner, employee, authorised vendor operator, etc.), with effective dates, status and authority scope.
5. **`identity_link_requests`** — pending claim/link requests, proof method, decision state, expiry, reviewer and reason. Never expose account existence or unmasked contact details to an unauthenticated requester.
6. **`identity_events`** — append-only audit of creation, verification, linking, unlinking, merge, split, status and contact changes. Capture actor, timestamp, reason, correlation/request ID and before/after metadata without storing OTPs, passwords or secrets.
7. **`identity_aliases`** — permanent historical identifiers/redirects for controlled merge resolution; never recycle an SBID.
8. **`identity_services`** (or equivalent typed extension tables) — loyalty membership/card and referral ownership references to SBID, retaining existing account/ledger IDs.

### 3.2 Profile IDs and account IDs

- SBID is the permanent platform party identifier.
- Customer ID, Employee ID and Vendor ID remain independently generated domain identifiers. Do not reuse numeric primary keys across domains or derive one from another.
- For a vendor organisation, Vendor ID belongs to the organisation SBID. Each human representative has their own individual SBID and a separately authorised relationship to that organisation.
- Login credentials/sessions remain in the existing authentication systems during the compatibility period. Login account IDs are not profile IDs or SBIDs.
- Admin is an access privilege, not a profile type. An individual may be Employee + Vendor representative + Customer and separately hold Admin permissions.
- A profile deactivation ends or suspends that relationship; it must not erase the party or business history.

### 3.3 Identity resolution rules

- Similar name, date of birth, address or contact similarity is a candidate signal only. It is never sufficient to merge identities.
- An authenticated existing account can initiate a link; prove control of the relevant account/contact before linking.
- New registration may show a privacy-safe possible-match prompt. It must not disclose whether a particular account exists, its full name, role, email, phone or other profile details.
- A verified email/phone is a contact-ownership signal, not by itself proof that two existing accounts belong to the same legal person when there is conflict, shared use or recycled contact risk.
- Use OTP or equivalent proof, authenticated session confirmation, and explicit confirmation for self-service links. Higher-risk cross-role links or organisation authority changes require authorised review.
- When proof is inconclusive, create a pending case or a separate SBID. Resolve later through a reviewed link/merge; never silently merge.
- Merge/split operations require dual-control for privileged/high-impact cases, reason capture, immutable event records, alias preservation, referential integrity and a rollback/recovery plan.

## 4. Backward-compatible integration design

- Customer registration: retain current endpoint and response contract where possible; call a shared identity resolver; preserve existing customer account ID, password hash/session behavior and referral code history.
- Employee invitation: keep current invitation token lifecycle; resolve/claim an individual SBID after the invitee proves invitation control; link the existing HR employee and `app_users` without changing their IDs.
- Vendor invitation: distinguish supplier organisation from human invitee; link the supplier to an organisation SBID and the invitee to an individual SBID; create an explicit authorised-representative relationship.
- CRM: retain `customer_account_customer_links`; add a profile link to the SBID and preserve existing verification metadata.
- Loyalty: add SBID association and a stable card lifecycle. Do not change transaction IDs, coin lots, accounting postings or historical balances. Card replacement deactivates the old card but never reuses its number.
- Referral: retain legacy codes and referral rows; map ownership to SBID; keep tracking and reward issuance separate and configurable.
- Admin: add a dedicated Identity Management workspace with search, masked contact views, profile IDs/statuses, link requests, relationship management and audit timeline. Apply current RBAC and least privilege.

## 5. Data migration and reconciliation plan

The source repository is not the live database. A data-level audit still needs a read-only, separately authorised production snapshot or secure export. No production access was used in this phase.

Before any migration:
1. Inventory live table definitions, constraints, indexes, row counts and migration ledger.
2. Profile duplicate and orphan candidates across `customer_accounts`, `customers`, `app_users`, `hr_employees`, `suppliers`, `vendor_portal_users`, loyalty and referral tables.
3. Report counts and masked candidate references only; do not export passwords, session tokens, OTPs, bank/PAN/Aadhaar data or full personal contact details into Git.
4. Classify matches as deterministic existing relationship, verified claim required, manual review required, or unresolved. Similarity alone never becomes an automatic merge.
5. Build a dry-run mapping report with source primary keys, proposed SBID, reason, confidence class and exceptions.
6. Verify row counts, uniqueness, FK coverage, balances, referral ownership, payroll/order/invoice links and authentication continuity.
7. Prepare additive migrations with a new unique migration number chosen only after checking the current maximum and governance ledger. Never edit an applied migration.
8. Back up and test restore before production rollout. Live migration requires separate explicit approval.

## 6. Risks and controls

| Risk | Required control |
|---|---|
| Wrong-person merge | Proof of ownership; manual review; no name-only merge |
| Shared/recycled mobile/email | Contact history and multi-owner/shared-contact support; verified ownership is time-bound |
| Account enumeration | Generic public responses; masked candidate prompt; rate limits |
| Privilege escalation | Separate profiles from RBAC; scoped organisation roles; re-authentication for sensitive changes |
| Vendor organisation/person confusion | Distinct organisation and individual SBIDs; explicit representative relationship |
| Lost loyalty balance/history | Preserve existing ledger/account IDs; reconciliation before and after linking |
| Referral abuse | Preserve reward policy and eligibility checks; no automatic staff/vendor rewards |
| Payroll/order/invoice breakage | Additive foreign-key mapping; preserve domain primary keys |
| Duplicate SBID/identifier under concurrency | Database unique constraints, transactions, deterministic locking/retry |
| Audit tampering | Append-only event model, restricted write path, actor attribution |
| Migration drift | New numbered migration, schema governance, dry-run, checksums and backups |

## 7. Test strategy and acceptance gates

Required automated coverage before declaring the system complete:

- SBID generation is unique under concurrent creation and permanent after deactivation.
- Individual and organisation party creation; organisation representative authorisation and expiry.
- Customer-only, employee-only, vendor-only, and combined Customer + Employee + Vendor profile mappings.
- Multiple verified contacts; unverified, shared and recycled contacts; contact replacement and history.
- Existing customer registration/login/session regression.
- Existing employee and vendor invitation acceptance/revocation/expiry regression.
- Authenticated link, OTP proof, wrong-account proof, expired proof, duplicate link and replay protection.
- Generic public duplicate response and account-enumeration resistance.
- Admin approval/rejection, reason capture, least-privilege enforcement and audit completeness.
- Merge/split alias behavior, rollback/recovery and no hard deletion.
- Loyalty card issue/replace/deactivate; unchanged points, transactions, coin lots and accounting entries.
- Referral code/link uniqueness, ownership, self-referral prevention and configurable rewards.
- Existing API contract tests, full backend test suite, both frontend builds, frontend unit/contract/route tests and browser workflows.
- Migration dry-run, empty database install, populated fixture migration, idempotency, concurrency and restore rehearsal.

Completion gate: no unresolved critical security issue, no unexplained source-row loss, all mapped relationships reconcile, no regression in customer/staff/vendor authentication, and all CI checks pass.

## 8. Work sequence after the audit

1. Finish the read-only data model inventory and approve the canonical schema/service contract.
2. Add the additive database foundation and migration tests on the feature branch.
3. Implement the shared identity service and its unit/integration tests.
4. Integrate customer, employee, vendor and CRM paths one at a time behind backward-compatible behavior.
5. Link loyalty and referral history without re-keying ledgers.
6. Build Identity Management UI and permission tests.
7. Run regression, security and migration rehearsal; open a reviewable PR.
8. Obtain separate production approval before any live database or deployment action.

## 9. Explicit limitations of this audit

- This audit is based on committed repository source and tests at the stated main SHA.
- It does not establish which migrations are applied in production or the live counts/quality of customer, employee, vendor, login, loyalty or referral data.
- It does not claim any production change, database migration, deployment or service restart.
- The current migration directory contains numbered files through `042_hr_attendance_controls.sql`; the eventual identity migration number must be selected against the current branch and schema governance checks at implementation time.
