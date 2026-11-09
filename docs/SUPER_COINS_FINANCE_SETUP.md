# Super Coins Finance setup

## Chart of accounts

The single additive migration `028_super_coins_checkout_redemption.sql` creates these accounts idempotently along with the redemption tables and does not rename or retype existing accounts:

| Code | Account | Type | Purpose |
|---|---|---|---|
| 2410 | Super Coins Outstanding Liability | Liability / current liability | Outstanding customer coin obligation |
| 4210 | Super Coins Breakage Income | Income / other income | Coins that expire unredeemed, subject to Finance policy |
| 6110 | Super Coins Reward Expense | Expense / operating | Cost of customer coin rewards |

The migration verifies that an existing account with one of these codes has the expected account type. It does not seed approved event mappings.

## Required effective-dated mappings

Create each mapping for legal entity `DEFAULT`, module `loyalty`, no tax component, and the Finance-approved effective date. Use the account codes above.

| Event type | Line role | Account code | Required account type |
|---|---|---:|---|
| points_earned | loyalty_reward_expense | 6110 | expense |
| points_earned | loyalty_points_liability | 2410 | liability |
| points_redemption | loyalty_points_liability | 2410 | liability |
| points_expired | loyalty_points_liability | 2410 | liability |
| points_expired | loyalty_breakage_income | 4210 | income |
| points_adjusted | loyalty_points_liability | 2410 | liability |
| points_adjusted | loyalty_adjustment_offset | 6110 | expense |
| points_redeemed_admin | loyalty_points_liability | 2410 | liability |
| points_redeemed_admin | loyalty_reward_expense | 6110 | expense |

## Accounting treatment

- Earn: debit 6110 and credit 2410.
- Website checkout redemption: debit 2410 in the sales voucher; this is not posted again as an admin redemption.
- Admin/manual redemption: debit 2410 and credit 6110, recognising the redemption against the previously accrued reward expense.
- Administrative debit correction: debit 2410 and credit 6110, reversing the reward expense associated with an erroneous/unearned credit.
- Expiry: debit 2410 and credit 4210, only after Finance has approved the breakage-income policy.

All postings are balanced and idempotent. Missing, inactive, ambiguous, or wrong-type mappings fail closed.

## Maker-checker operational procedure

1. Apply the required schema migrations through the approved deployment pipeline; do not run SQL manually against production.
2. Confirm accounts 2410, 4210 and 6110 exist, are active, and have the expected account types.
3. Create the nine mappings above as drafts through the existing `POST /api/accounting/event-mappings` API. Set the effective date approved by Finance; do not backdate without explicit approval.
4. Submit each draft through `POST /api/accounting/event-mappings/{mapping_id}/submit`.
5. A different Finance approver must approve each mapping through `POST /api/accounting/event-mappings/{mapping_id}/approve`. The maker cannot approve their own mapping.
6. Verify exactly one active approved mapping exists for each event/role/effective-date pair using `GET /api/accounting/event-mappings?source_module=loyalty&status=approved`.
7. Run disposable-database integration tests and a controlled non-production end-to-end test before enabling customer checkout redemption.

## Production gate

This document and the migration do not constitute live account creation or mapping approval. No production DB changes, approved mapping rows, deployment, or customer-facing enablement are performed by this PR. Finance approval and production preflight remain separate release gates.
