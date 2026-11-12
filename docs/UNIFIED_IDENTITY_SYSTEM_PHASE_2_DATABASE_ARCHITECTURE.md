# Unified Identity System — Phase 2 Database Architecture

**Status:** Architecture specification for implementation  
**Branch:** `feature/unified-identity-system`  
**Baseline:** `main` at `ef1de4682e8416edfd0db7d63ee3ecc7bab7bf41`  
**Production:** No live database or service changes are authorised by this document.

> **Historical design specification — implementation status has moved on.** The proposed schema/service design below is retained as the original Phase 2 architecture record. The implemented scope, current limitations and production gates are documented in [the current implementation guide](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md) and [production rollout runbook](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md). Do not treat proposed steps below as evidence that they remain unimplemented or as permission to change production.

## 1. Design principles

1. SBID is a permanent platform identity for one individual or one organisation.
2. Existing customer, CRM, employee, supplier/vendor, login, loyalty and referral records retain their current primary keys and domain ownership.
3. The identity layer links existing records to an SBID; it does not replace them or copy their transactional data.
4. Profile types and access permissions are different. Customer, Employee and Vendor are profile relationships. Admin, HR Manager, Finance Approver and similar capabilities are permissions/roles.
5. One person can have multiple profiles and multiple login accounts. An organisation has its own SBID; each human representative has their own SBID.
6. Contact details are not proof of identity by themselves. Names, addresses and matching phone/email values are candidate signals only.
7. Identity changes are transactional and auditable. No hard delete or silent merge.
8. All schema changes are additive, separately numbered and tested on disposable PostgreSQL before any production consideration.

## 2. Logical model

### 2.1 `identity_parties`

One row per individual or organisation.

| Column | Purpose |
|---|---|
| `id` | Internal bigint primary key |
| `sbid` | Public permanent identifier, unique and immutable (e.g. `SBID-<random-token>`) |
| `party_type` | `individual` or `organisation` |
| `display_name` | Current display/legal name; not a matching key |
| `status` | `active`, `inactive`, `merged`, `under_review` |
| `merged_into_party_id` | Optional canonical party pointer; populated only by audited merge |
| `created_at`, `updated_at` | Timestamps |

SBID generation must use a cryptographically secure random token, database uniqueness and bounded collision retry inside the creation transaction. Do not encode role, sequence, email, phone, date of birth or other personal data in SBID. SBID is never recycled. A merged SBID remains resolvable as a historical alias.

### 2.2 `identity_profiles`

Typed links to domain records. Each row belongs to one party and identifies exactly one source record:

- `customer_account_id` → `customer_accounts(id)`
- `crm_customer_id` → `customers(id)`
- `employee_id` → `hr_employees(id)`
- `supplier_id` → `suppliers(id)`

A CHECK constraint requires exactly one source key per row. Partial unique indexes prevent one domain record from being assigned to multiple parties. Multiple profile rows of different types may point to the same party. Domain IDs are not rewritten. Deactivation is represented by profile status and effective dates, not deletion.

The Vendor ID displayed to users is the existing stable supplier/vendor domain identifier. The organisation party is the SBID owner of that supplier profile. Do not invent a second Vendor ID or change supplier primary keys without a separately approved business requirement.

### 2.3 `identity_auth_accounts`

Links authentication accounts to a person/organisation party without replacing credentials or sessions:

- `account_type`: `customer` or `staff`
- `customer_account_id` or `app_user_id`: exactly one typed FK
- `party_id`: linked party
- `linked_at`, `linked_by`, `link_method`, `status`

Each authentication account can link to at most one party. A party can have multiple customer and/or staff auth accounts. Existing customer and staff session tokens remain valid and keep their current account IDs. Vendor portal access remains an authorisation relationship from the staff login to a supplier; it does not convert a supplier organisation into a human login.

### 2.4 `identity_contacts`

Stores contact points attached to a party:

- `contact_type`: email, phone or future supported type
- `normalized_value`, `display_value`
- `verification_status`: unverified, verified, expired, revoked
- `verified_at`, `valid_from`, `valid_to`
- `is_primary`, `source`, audit timestamps

Do **not** impose global uniqueness on email or phone across parties: households, shared business inboxes, recycled mobile numbers and family phones exist. Prevent duplicate active contact rows for the same party/type/normalised value. A contact can be shared by more than one party; sharing is not an identity merge. A contact's verification is time-bounded and revocable.

### 2.5 `identity_relationships`

Explicit links between parties, especially individual-to-organisation relationships:

- `from_party_id`, `to_party_id`
- `relationship_type`: representative, owner, director, employee, authorised_vendor_user, accountant, etc.
- `scope` (JSON object with constrained/validated permissions or a referenced permission policy)
- `valid_from`, `valid_to`, `status`
- `created_by`, `approved_by`, timestamps and reason

Relationship changes must not implicitly grant global admin permissions. Organisation authority is scoped to the specific organisation and capability.

### 2.6 `identity_link_requests`

Workflow for linking existing records or claiming a possible existing identity:

- requester party/account, target profile/account reference, requested action
- status: pending, proof_required, approved, rejected, expired, cancelled
- proof method and proof timestamp (never OTP value or secret)
- reviewer, reason, expiry, request/correlation ID
- created/updated timestamps

Public registration responses must not disclose whether a matching account exists or reveal its profile type, contact details or identity data. Use a generic response and a secure claim/recovery path.

### 2.7 `identity_events` and `identity_aliases`

Append-only event log records party/profile/contact/relationship/auth-link/request/merge/split lifecycle events. Capture actor, action, timestamp, reason, request/correlation ID and carefully minimised before/after JSON. Never store passwords, OTPs, session tokens, PAN/Aadhaar values or payment secrets.

Aliases preserve old SBIDs after a controlled merge. An alias points to a canonical party and cannot be reused for a new identity. Merge/split must be performed by a service transaction with full validation and event history; the database should prevent cycles and self-merges.

## 3. ID ownership and display

| Identifier | Owner/source | Relationship to SBID |
|---|---|---|
| SBID | `identity_parties` | Permanent master identity |
| Customer ID | Existing customer account / CRM domain identifier as displayed by that module | Linked profile; preserve existing IDs |
| Employee ID | `hr_employees.employee_code` | Linked profile; preserve existing code |
| Vendor ID | Existing `suppliers` identifier | Organisation profile; preserve existing ID |
| Login account ID | `customer_accounts.id` or `app_users.id` | Authentication key only; not a profile ID |
| Loyalty card number | Existing `loyalty_accounts.card_number` | Loyalty membership associated with SBID |
| Referral code | Existing customer referral code initially | Referral programme identifier associated with SBID |

A party may have no profile, one profile or many profiles. The identity register must show missing profile IDs as empty rather than manufacture placeholder profiles.

## 4. Loyalty and referral compatibility

- Add an SBID association to the loyalty account (or a dedicated loyalty-membership association) without changing `loyalty_accounts.id`, `customer_email`, card numbers, transaction IDs or coin allocation references.
- A loyalty account can have a card lifecycle: active, replaced, suspended, expired, revoked. Historical card numbers are never reassigned.
- Card replacement creates a new card record or card-history row and preserves the same loyalty account and ledger.
- Existing referral codes and `customer_referrals` rows remain intact. Add an SBID owner mapping for referrer and referred parties; preserve historical customer-account references.
- Referral rewards remain policy-driven and independent of employee/vendor status. Do not add a default staff/vendor reward.
- Avoid a broad rewrite of loyalty lookup endpoints during the first migration. Keep existing email/order verification paths operational while introducing SBID-aware resolution.

## 5. Data constraints and transaction rules

- SBID unique, NOT NULL and immutable.
- Exactly one party type per party.
- Exactly one typed source FK per profile/auth-link row.
- Unique mapping from each existing source record to one party.
- A single active primary email and phone per party/type where the business policy requires it; allow multiple verified contacts and shared contact values across parties.
- No contact uniqueness rule that incorrectly treats a shared/recycled value as proof of one person.
- FK deletion policies use RESTRICT for identity-bearing business records; identity history is retained.
- Unique idempotency/request keys for link and merge operations.
- Row-level/advisory locking and unique constraints protect concurrent linking; application-only "check then insert" is insufficient.
- Every link/unlink/merge/contact verification and relationship authority change writes an audit event in the same transaction.
- Audit event update/delete is denied to the application role; use a narrowly scoped database trigger/privilege design.
- Merge target cannot be inactive/merged; no self-merge, cycles or reuse of historical SBIDs.

## 6. Migration sequence (proposed)

1. Add identity foundation tables, constraints, indexes, ID generator and audit protection. No existing data is modified.
2. Add nullable identity references/associations to existing records only if a typed mapping table cannot safely provide the required relation. Prefer mapping tables to invasive alterations.
3. Backfill deterministic existing relationships only (e.g. existing invitation links). Do not auto-merge based on matching names or contacts.
4. Produce a separate dry-run report for ambiguous candidate matches; require verified claim or manual review.
5. Add service-level dual-write/linking for new records while legacy APIs continue to function.
6. Link loyalty/referral accounts and verify ledger/reward reconciliation.
7. Add admin register and review workflows.
8. Only after complete test/restore rehearsal and separate approval, schedule production rollout.

No production backfill is part of Phase 2 development. A migration file must be numbered after checking the live governance ledger and current main branch at implementation time. Existing numbered migrations are immutable.

## 7. API/service contract

Create one `IdentityService` boundary used by customer registration, employee invitations, vendor invitations, CRM linking, loyalty and the admin identity workspace. Core operations:

- `create_party(party_type, display_name, actor)`
- `register_profile(party_id, profile_type, source_id, actor)`
- `link_auth_account(party_id, account_type, account_id, proof, actor)`
- `add_contact(party_id, type, value, verification, actor)`
- `request_link(...)`, `approve_link(...)`, `reject_link(...)`
- `create_relationship(...)`, `revoke_relationship(...)`
- `merge_parties(source_party_id, target_party_id, proof, reason, actor)`
- `resolve_sbid(sbid)`, `get_identity_register(filters, actor)`

The service owns transaction boundaries and writes identity events. API handlers must not implement separate matching rules or write identity tables directly. Keep current endpoints and payloads backward-compatible; add optional identity metadata only where clients can safely ignore it.

## 8. Security and privacy requirements

- Never return unmasked matching identity details to an unauthenticated registration form.
- Rate-limit registration, lookup, OTP and link-request endpoints; use generic errors and replay-resistant expiring proof tokens.
- Require re-authentication/step-up proof for account linking, contact changes, merge/split and organisation authority changes.
- Admin search and contact reveal must be permission-gated and audited. Default views show masked contacts.
- Do not put sensitive personal data or identity exports in Git commits, CI logs or ordinary application logs.
- Apply data minimisation, purpose limitation, retention and access controls consistent with India's applicable privacy law and rules; obtain legal review before setting retention periods or collecting additional identity attributes.

## 9. Open implementation decisions (must be settled by code/schema review, not guessed)

1. SBID token length/alphabet and whether external users see the raw SBID or a separate public reference.
2. Whether CRM customer ID is shown alongside storefront customer account ID or the UI presents one canonical Customer ID label.
3. Whether a supplier/vendor organisation can have multiple supplier records per legal entity and therefore multiple Vendor profile links to one organisation SBID.
4. The authorised evidence and approval matrix for high-risk identity claims and organisation ownership changes.
5. Exact contact sharing and primary-contact policy.
6. Loyalty card history model: new card-history table versus current card number plus a separate immutable card issuance table.

These decisions do not block creating the additive party/profile/contact/audit foundation, but must be resolved before portal, loyalty and admin UI integration.
