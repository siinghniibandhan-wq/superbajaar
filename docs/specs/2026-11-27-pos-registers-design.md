# POS register and cashier shift implementation

**Date:** 27 November 2026  
**Branch:** `feature/pos-register-workspace`  
**Scope:** POS register lifecycle, cashier shifts, cash drawer and workspace integration.

## Operating model

- A store/location can have multiple independent POS registers.
- Each register has a unique code within its store and may have only one open shift.
- A cashier may have only one open shift across all registers.
- A cashier must have an active shift on the selected register before creating a POS sale.
- POS orders retain the register shift ID, so captured cash tenders can be reconciled against the correct drawer.

## Implemented in this branch

1. Register setup by manager/admin, with register code, name and store location.
2. Cashier shift opening with opening float; manager can open a shift for another cashier through the API.
3. Cash-in and cash-out movements with mandatory reason and optional reference.
4. Cash tender confirmation restricted to the owning open shift (or manager); non-cash tenders cannot use this endpoint.
5. Shift close with expected cash, physical counted cash and calculated variance.
6. Read access to current shift, cash movement history and recent closed-shift reconciliation history.
7. Append-only cash movement and register audit records enforced by database triggers.
8. POS UI register selection, shift open/close, cash movement controls, cash confirmation, shift history and barcode/SKU search.

## Cash reconciliation formula

`Expected cash = opening float + captured cash sales - recorded cash refunds + cash in - cash out`

`Variance = counted cash - expected cash`

The backend uses decimal arithmetic and records both expected and counted values at close. A closed shift is immutable through the API; a correction is represented by a separate compensating record rather than editing history.

## Release requirements

- Migration `065_pos_register_shifts.sql` is added to `backend/schema_required.txt`.
- Run the complete backend test suite and frontend unit/route/build checks in CI.
- Review permission grants and confirm the cashier/manager role mapping.
- Back up the production database before applying migration 065.
- Apply migration only through the approved deployment/migration workflow; do not apply it as part of this code change.
- Run controlled test sales at two registers, cash-in/out, cash confirmation, shift close and variance checks before production use.

## Not claimed as complete by this change

The following remain separate POS/payment work: provider-connected UPI/card terminal confirmation, split tenders, discounts/manager price overrides, GST invoice/receipt printing, returns/refunds and refund settlement, customer/loyalty lookup, offline queueing and hardware-specific barcode/receipt-printer integrations. Existing payment-provider and refund limitations remain in force.
