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

## Storefront, warehouse and fulfilment relationship

### Existing verified behavior
- Website checkout requires a verified six-digit delivery PIN and does not accept a customer-supplied stock location ID.
- The backend selects an active `stock_locations` record where `pin_code` matches and `is_fulfillable=TRUE`.
- The current reservation helper evaluates eligible locations in ascending ID order and reserves the complete order at the first single location that has every requested variant and sufficient available quantity.
- The current selector does not use warehouse address/distance, facility type, operating hours, capacity, or an explicit priority. It does not split one order across multiple facilities.
- The selected location ID is retained in inventory reservation movements; fulfilment picking/dispatch consumes those location-specific reservations. Thus the selected stock location is the operational fulfilment origin.

### Required behavior for the completed warehouse profile
- A facility must be explicitly enabled for storefront fulfilment; retain the existing `is_fulfillable` contract as the compatibility switch.
- Delivery PIN coverage must be configurable as one or more service PIN codes per facility, rather than assuming a single warehouse PIN is sufficient. Keep the existing `stock_locations.pin_code` value as the legacy/default service PIN during rollout.
- Add a clear facility routing priority and optional operational availability/capacity controls. Do not silently treat storage capacity as live available capacity unless inventory reservations/operations maintain that figure.
- At checkout, the backend—not the browser—must select the fulfilment facility using the verified delivery PIN, active status, fulfilment eligibility, operating availability, stock availability for every order line, and configured priority. Address/distance ranking can be a later phase once reliable customer delivery coordinates and geocoding exist; do not invent distances from PIN codes.
- Preserve the current safe all-lines-at-one-facility rule in the first implementation. Do not split orders across warehouses or stores in this change.
- Persist the selected facility through the existing inventory reservation and fulfilment records. Show the assigned fulfilment facility in admin order/fulfilment views so staff can identify the dispatch origin.
- If no single eligible facility can fulfil the order, return a clear checkout message; never reserve partial stock or silently choose a non-fulfillable location.
- POS continues to use the staff-selected stock location. Website checkout continues to select server-side. Manual order rules remain unchanged.

### Acceptance criteria for storefront integration
- A facility not marked fulfilment-eligible cannot receive website reservations.
- A facility serving the customer's verified delivery PIN can receive a reservation only if it has all requested variants and sufficient available quantity.
- Facility priority/availability affects server-side selection deterministically; the browser cannot override the selected facility.
- Existing legacy facilities and existing orders/reservations remain valid.
- The assigned facility is visible to fulfilment staff and the same location is used for pick/dispatch.
- No multi-facility split allocation, distance-based routing, storefront redesign, or change to POS selection is included in this phase.
