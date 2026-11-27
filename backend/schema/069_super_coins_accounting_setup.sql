-- 069: Seed safe, reviewable Finance mappings for the Super Coins lifecycle.
-- Additive and idempotent. Suggested mappings remain DRAFT until a maker submits
-- them and a different authorised Finance user approves them. No ledger history
-- is created or altered by this migration.

INSERT INTO public.accounting_accounts
    (code, name, account_type, sub_type, is_system, description)
VALUES
    ('2600', 'Customer loyalty points liability', 'liability', 'current_liability', true,
     'Outstanding Super Coins owed to customers; ₹1 per coin'),
    ('6110', 'Customer loyalty rewards expense', 'expense', 'operating', true,
     'Cost of Super Coins earned or redeemed by customers'),
    ('4210', 'Expired customer rewards breakage income', 'income', 'other_income', true,
     'Breakage income only when an eligible Super Coins balance legally expires')
ON CONFLICT (code) DO NOTHING;

-- These are proposals, not approvals. The effective date covers existing
-- historical loyalty transactions that may still need their first accrual.
INSERT INTO public.accounting_event_account_mappings
    (legal_entity_code, source_module, event_type, line_role, account_id,
     tax_component, effective_from, status, source_reference, notes)
SELECT
    'DEFAULT', 'loyalty', seed.event_type, seed.line_role, account.id,
    NULL, DATE '2000-01-01', 'draft', 'seed:super-coins-accounting-setup:v1',
    'Suggested system mapping. Review the chart of accounts, submit this draft, and obtain approval from a different authorised Finance user.'
FROM (VALUES
    ('points_earned', 'loyalty_reward_expense', '6110', 'expense'),
    ('points_earned', 'loyalty_points_liability', '2600', 'liability'),
    ('points_redemption', 'loyalty_points_liability', '2600', 'liability'),
    ('points_redeemed_admin', 'loyalty_points_liability', '2600', 'liability'),
    ('points_redeemed_admin', 'loyalty_reward_expense', '6110', 'expense'),
    ('points_adjusted', 'loyalty_points_liability', '2600', 'liability'),
    ('points_adjusted', 'loyalty_adjustment_offset', '6110', 'expense'),
    ('points_expired', 'loyalty_points_liability', '2600', 'liability'),
    ('points_expired', 'loyalty_breakage_income', '4210', 'income')
) AS seed(event_type, line_role, account_code, expected_account_type)
JOIN public.accounting_accounts account
  ON account.code = seed.account_code
 AND account.account_type = seed.expected_account_type
 AND account.is_active = TRUE
WHERE NOT EXISTS (
    SELECT 1
    FROM public.accounting_event_account_mappings existing
    WHERE existing.legal_entity_code = 'DEFAULT'
      AND existing.source_module = 'loyalty'
      AND existing.event_type = seed.event_type
      AND existing.line_role = seed.line_role
      AND existing.tax_component IS NULL
      AND existing.status IN ('draft', 'in_review', 'approved')
      AND daterange(existing.effective_from, COALESCE(existing.effective_to, 'infinity'::date), '[]')
          && daterange(DATE '2000-01-01', 'infinity'::date, '[]')
);
