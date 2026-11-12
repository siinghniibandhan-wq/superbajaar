# Unified Identity System — implementation and operations

**Documentation status:** Current implementation reference for the merged source on `main`  
**Last updated:** 12 November 2026  
**Code baseline:** PR #58 merge commit `f0182f083a4e34d3c07411b8433c9217b7c4024b`  
**Production status:** Not verified by this document. No production migration, deployment, data backfill or AWS operation is authorised here.

> This guide supersedes the implementation-status conclusions in the Phase 1 audit and the proposed-work sequencing in the Phase 2 architecture specification. Those documents are retained as historical design/audit records, not as the current status.

## 1. Executive status

The first implementation tranche of the Unified Identity System is merged into `main` through:

| PR | Scope | Merge status |
|---|---|---|
| [#54](https://github.com/siinghniibandhan-wq/superbajaar/pull/54) | SBID creation, HR employee and supplier organisation profile onboarding, Identity Register and admin profile-link review | Merged |
| [#55](https://github.com/siinghniibandhan-wq/superbajaar/pull/55) | Read-only legacy reconciliation preview, customer identity claims/history, representative relationships and review workflows | Merged |
| [#57](https://github.com/siinghniibandhan-wq/superbajaar/pull/57) | Administrator-reviewed contact verification, relationship revocation and audit visibility | Merged |
| [#58](https://github.com/siinghniibandhan-wq/superbajaar/pull/58) | Customer-owned claim cancellation, immutable cancellation event and per-identity claim submission rate limit | Merged |

PR #58 was squash-merged as commit `f0182f083a4e34d3c07411b8433c9217b7c4024b`. The PR's recorded CI, security, database, browser-quality and schema-governance checks completed successfully before merge. A green PR check is not evidence that the production release or production database has changed.

### Status vocabulary

- **Merged:** code is present in the GitHub `main` branch.
- **CI-verified:** the named automated checks completed for the relevant PR head.
- **Deployed:** the relevant artifact has been released to a named environment and verified there.
- **Migrated:** the target database's `schema_migrations` ledger records the exact migration filename and SHA-256.
- **Reconciled/backfilled:** legacy records have been linked using an approved process and counts have been independently reconciled.

Only the first two states are established by the PR records above. Deployment, production migration and production reconciliation must remain marked **not verified / pending** until fresh operational evidence is collected. The documentation commit `dbe9a7949e72a961afda2a628eb24983c1b3d828` triggered the broad `deploy.yml` push workflow; run `43156606739` was explicitly cancelled while only its source-verification job was running and before either EC2 deploy or Amplify verification/restore job started. No deployment was performed by that run.

## 2. Identity model and identifier ownership

The identity layer adds a platform-level identity without replacing the existing domain records.

| Concept | Canonical source | Rule |
|---|---|---|
| SBID | `identity_parties.sbid` | Permanent public identity reference for one individual or organisation; unique and immutable |
| Party | `identity_parties` | Party type is `individual` or `organisation` |
| Customer profile | `identity_profiles.customer_account_id` | Existing customer account ID remains unchanged |
| CRM profile | `identity_profiles.crm_customer_id` | Existing CRM customer ID remains unchanged |
| Employee profile | `identity_profiles.employee_id` | Existing HR employee ID/code remains unchanged |
| Vendor organisation profile | `identity_profiles.supplier_id` | Existing supplier/vendor ID remains unchanged |
| Login | `identity_auth_accounts` | Links an existing customer or staff login to an individual party; does not replace credentials/session IDs |
| Loyalty association | `identity_loyalty_accounts` | Associates an existing loyalty account with a party; existing loyalty account/card/ledger identifiers remain intact |
| Referral association | `identity_referral_links` | Associates an existing referral record with referrer/referred parties; existing referral record remains intact |

An individual and an organisation are distinct parties. A human representative has their own individual SBID and an explicit relationship to the organisation SBID. An organisation must not share a human's SBID.

## 3. Current implemented capabilities

### 3.1 Party and profile onboarding

- Identity parties receive generated SBIDs when created through the integrated onboarding paths.
- HR employee creation creates/reuses an individual identity and employee profile association.
- Supplier master creation creates/reuses an organisation identity and vendor-organisation profile.
- Vendor portal invitation acceptance can associate the human representative through an explicit relationship rather than treating the organisation as a human login.
- Existing domain primary keys are preserved.

### 3.2 Identity Register and administration

- Admin Identity Register supports search, party-type filtering and server-side pagination.
- Identity detail includes profile, login, contact, loyalty/referral association, relationship and audit information where present.
- Admin-submitted profile-link requests enter a review workflow.
- Rejections require a reason.
- Admin review actions are permission-gated; the contact/relationship controls added in PR #57 require the appropriate `approve` permission.
- Contact values are masked in the relevant identity detail views.

### 3.3 Legacy reconciliation

- A read-only preview identifies possible cross-source matches using normalized contact candidates.
- Preview results are candidates for human review, not proof of common ownership.
- Existing SBIDs and source references are surfaced to support review.
- No automatic profile linking or party merging is performed by the preview.
- A legacy match must not be approved solely because a name, email or phone number matches. Recycled numbers, family contacts and shared business inboxes are possible.

### 3.4 Customer identity claims

- An authenticated customer can submit a claim for an existing SBID.
- Customers can view their own claim history and status.
- Claim history remains accessible through approved identity consolidation aliases.
- A customer may cancel only their own unreviewed claim in `pending` or `proof_required` status.
- A reviewed claim cannot be cancelled; attempts return a conflict response.
- Cancellation retains the request history and writes a `link_cancelled` identity audit event.
- Claim submissions are rate-limited to five per canonical identity per hour, including aliases.
- The cancellation endpoint is scoped to the authenticated customer route; customers cannot cancel another customer's claim.

### 3.5 Contact verification and organisation relationships

- Administrators can mark an eligible current email/phone contact as verified after reviewing evidence.
- Verification records the proof method, reason, timestamp and audit event.
- Supported administrative evidence methods in the service include document review, in-person review, verified account and business registry.
- This is **not** an automated OTP verification or document-upload workflow.
- Administrators can revoke an active organisation relationship with a required reason.
- Revocation preserves the relationship record and records an audit event; it is not a hard delete.
- Relationship changes are visible in the relevant identity audit views.

### 3.6 Loyalty and referral association foundation

Migration 044 adds the association tables for existing loyalty accounts and referral records. The migration explicitly does not rewrite existing loyalty accounts, card numbers, balances, ledgers, referral codes or rewards. The presence of the tables in source does not prove that historical records have been linked or reconciled in production.

## 4. Database migrations

The identity tranche requires the following additive schema migrations:

| File | Purpose |
|---|---|
| `043_unified_identity_foundation.sql` | Core parties, profiles, authentication links, contacts, relationships, requests, events and aliases |
| `044_identity_loyalty_referral_links.sql` | Invitation representative metadata and loyalty/referral identity associations |
| `045_identity_claim_cancellation_event.sql` | Allows `link_cancelled` in the identity event type constraint |

All three filenames are listed in `backend/schema_required.txt`. They must be treated as immutable after release/application. Do not renumber, edit or reapply a changed version. Any correction requires a new unused migration number.

Migration files are source code, not proof of application. A migration is considered applied only when the intended database's ledger records the expected filename and checksum and the schema is independently checked.

See [Database Migrations](DATABASE_MIGRATIONS.md) and the [production rollout runbook](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md).

## 5. Security, privacy and operational invariants

1. A contact match is a candidate signal, not identity proof.
2. Do not reveal whether an unrelated customer account exists through public registration or claim responses.
3. Preserve existing customer and staff authentication flows and identifiers.
4. Keep individual and organisation parties separate; represent authority through scoped relationships.
5. Require a reviewer, evidence method and reason for privileged manual verification/review operations.
6. Preserve identity request and relationship history; do not hard-delete audit-relevant rows.
7. Never store passwords, OTP values, access tokens, PAN/Aadhaar values or payment secrets in identity events.
8. Mask contact values in ordinary admin views and audit access to sensitive identity data.
9. Apply least-privilege permissions; an organisation relationship must not grant global admin privileges.
10. Do not perform automated merges or bulk linking based on matching contacts.

India privacy-law applicability, purpose limitation, retention periods, notices and data-subject request procedures require a separate legal/compliance review before expanding identity data collection or retention.

## 6. Known limitations and work still requiring separate implementation/verification

The following must not be represented as complete merely because the identity foundation is merged:

- No production migration 043–045 is confirmed by the repository evidence.
- No production application deployment is confirmed by the repository evidence.
- No production legacy reconciliation/backfill is confirmed.
- The reconciliation preview does not itself approve or link candidate records.
- The PRs do not establish automated OTP verification, automated document verification or automatic identity matching.
- The association schema does not prove every historical loyalty/referral record is linked to an SBID.
- A production data-quality report is still required to measure unlinked profiles, duplicate candidates, conflicting links and unresolved claims.
- Full production restore rehearsal and post-migration reconciliation remain required.
- End-to-end acceptance must cover customer, staff/employee, supplier representative, admin reviewer, loyalty and referral paths in a production-like environment.

## 7. Acceptance checklist for rollout

- [ ] Confirm the exact `main` commit to release.
- [ ] Confirm backend and frontend release artifacts and deployment workflow targets.
- [ ] Confirm migrations 043–045 are present in the deployed checkout.
- [ ] Inspect the effective systemd schema service and timer; verify the timer is status-only.
- [ ] Confirm the production database target explicitly; do not rely on the runner's default `sb_app`.
- [ ] Run production `--status` and `--dry-run` only after confirming the target and access path.
- [ ] Review migration diffs and dependencies.
- [ ] Verify a fresh, readable pre-migration backup and recovery plan.
- [ ] Obtain separate explicit approval before the apply command.
- [ ] Apply through the controlled runner, not by pasting SQL manually.
- [ ] Verify ledger filenames and SHA-256 checksums for 043, 044 and 045.
- [ ] Verify API health, customer claim submit/history/cancel, admin review, contact verification and relationship revocation.
- [ ] Reconcile source and identity profile counts; document exceptions.
- [ ] Verify storefront and admin frontend deployment independently.
- [ ] Record release SHA, migration backup name, logs, test results and operator approval.

## 8. Related source and history

- [PR #54 — onboarding and admin workflows](https://github.com/siinghniibandhan-wq/superbajaar/pull/54)
- [PR #55 — reconciliation and customer claim workflows](https://github.com/siinghniibandhan-wq/superbajaar/pull/55)
- [PR #57 — contact verification and relationship lifecycle](https://github.com/siinghniibandhan-wq/superbajaar/pull/57)
- [PR #58 — customer claim lifecycle controls](https://github.com/siinghniibandhan-wq/superbajaar/pull/58)
- [Phase 1 audit (historical baseline)](UNIFIED_IDENTITY_SYSTEM_PHASE_1_AUDIT.md)
- [Phase 2 database architecture (design specification)](UNIFIED_IDENTITY_SYSTEM_PHASE_2_DATABASE_ARCHITECTURE.md)


## 6.1 Reconciliation preview fallback correction (PR #56)

The reconciliation preview reads optional legacy contact fields through JSON access so it can tolerate schema variations across historical customer, CRM, employee and supplier tables. Contact fallback must treat an empty or whitespace-only preferred field as absent; SQL `COALESCE` alone does not do this because an empty string is non-NULL.

The PR #56 correction applies `NULLIF(trim(value), '')` to preferred and fallback contact fields before selecting the first available value. This ensures that a blank `phone`, `email` or other preferred column does not hide a populated legacy fallback such as `mobile`, `mobile_number`, `customer_email`, `customer_phone` or `work_email`.

The regression contract test checks that the reconciliation query explicitly handles blank preferred values. The preview remains read-only: this correction changes candidate discovery only and does not verify contact ownership, approve a match, link profiles, merge parties or alter source records.

**Change status:** PR #56 is an open draft at the time this documentation was prepared. Treat the correction as proposed until its PR checks pass and it is merged. No production deployment, database migration or reconciliation run is implied.
