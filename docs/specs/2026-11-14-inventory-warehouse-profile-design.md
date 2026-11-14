# Warehouse Profile Completion — Design

Date: 2026-11-14
Repository: `siinghniibandhan-wq/superbajaar`
Scope: Inventory facility creation only.

## Goal
Replace the current minimal facility registration form with a complete, validated warehouse/store/dark-store profile while preserving existing stock-location identity and all existing inventory workflows.

## User experience
Keep the existing **Create warehouse / store** section and the separate **Warehouse storage locations** hierarchy. Organize the registration form into sections:

1. **Basic details (required):** name, facility type (warehouse/store/dark_store), unique facility code, active status.
2. **Address (required):** address line 1, city, state, PIN code, country. Address line 2, district and GPS coordinates are optional.
3. **Contact (optional):** manager/contact name, phone, email and emergency contact.
4. **Operations (optional/configurable):** capacity and unit, operating days/hours, receiving capability, dispatch capability, and fulfilment eligibility.
5. **Ownership & compliance:** legal establishment is required for controlled inventory operations; GSTIN and licence/registration references are optional and validated when supplied.

Use conditional labels for warehouse/store/dark-store where appropriate. Keep the current eligibility behavior and make the effect of fulfilment eligibility clear. Provide edit/view support for saved facility profiles so users can correct details after creation.

## Data and API design
- Preserve `stock_locations` as the canonical facility record and preserve its IDs and existing columns/contracts.
- Add a one-to-one facility-profile table through a new uniquely numbered SQL migration. It references `stock_locations(id)`; no destructive migration or backfill that changes stock ownership.
- Extend the existing facility create/read/update API compatibly. Existing clients and old records must continue to work; profile fields are additive.
- Validate required address fields, Indian PIN format, email/phone formats, positive capacity, unique facility code, and establishment ownership/authorization on the server.
- Save the stock location and profile atomically. If profile persistence fails, do not leave a partially created facility.
- Existing facilities without profile rows remain visible and operational; show a clear “Profile incomplete” state and allow completion/editing.
- Do not change internal-location endpoints, stock balances, movements, costing, approvals, fulfilment or purchasing logic.

## Acceptance criteria
- A user can create a facility with required basic/address/ownership data and optionally add operational/contact/compliance details.
- Duplicate facility codes and invalid required fields are rejected with actionable messages.
- Existing facilities and stock remain intact and readable.
- Existing internal storage hierarchy continues to use the same facility IDs and APIs.
- Facility profile can be viewed and edited without changing stock-location identity.
- No changes to unrelated inventory workflows or storefront behavior.

## Testing and rollout
- Add backend tests for create/read/update, validation, duplicate code, authorization, transaction rollback and legacy facilities.
- Add frontend tests for required-field validation, optional fields, create/edit states and preservation of the storage hierarchy.
- Run focused tests, the existing frontend unit/contract tests, frontend production build and relevant backend regression tests.
- Add the migration to `backend/schema_required.txt` in the same PR. Do not alter the schema runner or its automation.
- Do not apply production migrations or merge to `main` without explicit user approval.
