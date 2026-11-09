# Return inventory Accounting mapping approval

Migration `032_fulfilment_returns_and_split_dispatch.sql` adds the dedicated write-off ledger and seeds four **draft** mappings for each existing legal entity (plus the `DEFAULT` entity). Drafts are not active posting configuration.

## Required chart of accounts

| Code | Account | Use |
|---|---|---|
| 1200 | Inventory - stock in hand | Debit returned recoverable inventory |
| 5000 | Cost of goods sold | Credit to reverse original COGS |
| 5020 | Inventory write-off expense | Debit non-recoverable returned stock |

## Mapping sets

For each originating legal entity, Finance must approve all four rows:

| Event | Role | Account |
|---|---|---|
| `inventory_return` | `inventory_asset` | 1200 |
| `inventory_return` | `inventory_cogs_reversal` | 5000 |
| `inventory_return_writeoff` | `inventory_return_writeoff_expense` | 5020 |
| `inventory_return_writeoff` | `inventory_cogs_reversal` | 5000 |

The first event covers restock, quarantine and repair, which restore a valued inventory asset. The second covers write-off, which does not increase stock and instead recognises an expense.

## Maker-checker approval

1. Deploy schema through the approved release pipeline. Do not apply this migration manually to production.
2. In Accounting → Posting rules, filter the seeded inventory return mappings.
3. Review the legal entity, role, account, effective date and business rationale. Submit each draft for review.
4. A different authorised owner/admin Finance approver signs in and approves each in-review mapping. The maker or submitter cannot approve their own mapping.
5. Confirm all four rows show `approved` for the legal entity and effective date that will originate the return.
6. Verify the effective approved mappings through `GET /api/accounting/event-mappings?source_module=inventory&status=approved`.

The application resolves mappings using the legal entity on the original dispatch stock location and the posting date. Missing, ambiguous or not-yet-approved mappings block posting and roll back inventory changes. Do not backdate or alter the effective date without Finance approval.

## Production control

This migration seeds drafts only. Return posting remains fail-closed until Finance completes the maker-checker process. A successful CI test using isolated test mappings is not a production Finance approval.
