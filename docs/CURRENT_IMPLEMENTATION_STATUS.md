# Current implementation status and known gaps

**Reviewed:** 27 November 2026  
**Scope:** GitHub `main` source code and committed documentation.  
**Not covered:** Live EC2 state, production database migration ledger, deployed frontend/backend versions, provider accounts or end-to-end production transactions.

This document separates implemented code from workflows that are still incomplete. A route, screen or migration existing in Git is not proof that it has been deployed or verified in production.

## Implemented capabilities visible in source

- FastAPI registers the catalogue, inventory, orders, payments, Razorpay, delivery, fulfilment, customers, identity, purchasing, HR, staff/customer authentication, loyalty, reviews, accounting, organisation policy, pricing, POS and reports routers.
- Purchasing replenishment has migration 048, a backend service, API endpoints and a Purchasing workspace tab. It creates draft purchase requisitions for review; it does not auto-submit purchase orders.
- POS checkout creates an order and a pending tender atomically. Electronic tender remains pending until provider verification; cash requires authorised confirmation.
- Delivery supports shipment records, assignment, tracking/status updates and status history.
- Razorpay capture is provider-verified. Payment reconciliation reports application-recorded payment states.
- Customer identity verification includes email OTP flows.
- HR source includes employee, payroll, attendance, shift and scheduling workflows, plus statutory reconciliation export.

## Confirmed functional gaps

| Area | Current code behaviour | Missing / not yet implemented |
|---|---|---|
| POS register controls | Order checkout and pending tender creation exist. | Register sessions, cash-drawer opening/closing and shift cash reconciliation. The POS UI itself states these controls are still required. |
| Refunds and settlements | Payment statuses include refunded; payment records can be reconciled at application-record level. | A controlled provider refund-request/refund API, settlement batches, provider fees, chargeback handling and bank-deposit reconciliation. A recorded refunded status is not proof that a provider refund occurred. |
| Delivery carriers | Internal shipment assignment, tracking and status history are available. | Carrier-provider integrations, label generation and carrier webhook/status synchronization. The Delivery workspace explicitly says carrier integrations are not enabled. |
| Identity OTP channels | Customer email OTP is implemented for email verification and identity-claim confirmation. | SMS, WhatsApp and Telegram OTP delivery/verification channels. Do not represent these channels as active. |
| HR statutory compliance | Payroll and statutory reconciliation data/export are available. | Direct statutory portal filing/acknowledgement is not implemented by the CSV export. Final-settlement items such as gratuity and leave encashment remain manager-entered and require HR/CA review rather than automatic legal eligibility/formula determination. |

## Important interpretation

- These are functional workflow gaps, not merely missing labels in documentation.
- The absence of a feature in this list does not certify that every other module is complete. Cross-module permissions, data integrity, failure handling and end-to-end workflows still require dedicated tests.
- The five schema files added to `backend/schema_required.txt` on 27 November 2026 are release-gate manifest entries only. That change does not execute migrations or alter database state.
- Migration 048 being present in Git does not establish that it is applied in production.
- Production readiness must be confirmed independently using the deployed commit, migration ledger/checksums, service health and controlled end-to-end tests.

## Recommended implementation order

1. POS register sessions and auditable cash-drawer/shift close.
2. Provider refund lifecycle and settlement reconciliation.
3. Carrier integration framework and one carrier adapter at a time.
4. Additional OTP channels after provider, consent, abuse controls and delivery monitoring are selected.
5. Statutory filing integrations only after legal entity, jurisdiction, portal/API eligibility and CA-reviewed calculations are defined.

## Evidence reviewed

- `backend/app/main.py` — router registration.
- `backend/app/api/payments.py` and `frontend/src/features/payments/PaymentsWorkspace.jsx` — payment status and reconciliation limitations.
- `backend/app/api/delivery.py` and `frontend/src/features/delivery/DeliveryWorkspace.jsx` — internal delivery workflow and carrier limitation.
- `backend/app/api/customer_identity_verification.py` — email-only OTP delivery paths.
- `frontend/src/features/pos/POSWorkspace.jsx` — pending tender behaviour and explicit register-control limitation.
- `backend/app/api/hr.py` and the HR implementation notes in the root README — shift/attendance and payroll boundaries.
- `backend/schema/048_purchasing_replenishment.sql`, `backend/app/services/purchasing_replenishment.py`, `backend/app/api/purchasing.py` and `frontend/src/features/purchasing/ReplenishmentWorkspace.jsx` — replenishment implementation surfaces.
