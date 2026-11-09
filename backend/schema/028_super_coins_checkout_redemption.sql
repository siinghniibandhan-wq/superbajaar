-- 028: atomic Super Coins checkout redemption, expiry and cancellation restoration.
-- Additive and idempotent. Existing loyalty transactions and schema files are preserved.

ALTER TABLE IF EXISTS public.orders ADD COLUMN IF NOT EXISTS checkout_idempotency_key text;
ALTER TABLE IF EXISTS public.orders ADD COLUMN IF NOT EXISTS checkout_payload_hash char(64);
CREATE UNIQUE INDEX IF NOT EXISTS orders_checkout_idempotency_key_uidx
    ON public.orders (checkout_idempotency_key) WHERE checkout_idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.loyalty_order_redemptions (
    id bigserial PRIMARY KEY,
    order_id bigint NOT NULL UNIQUE REFERENCES public.orders(id) ON DELETE RESTRICT,
    account_id bigint NOT NULL REFERENCES public.loyalty_accounts(id) ON DELETE RESTRICT,
    redemption_transaction_id bigint NOT NULL UNIQUE REFERENCES public.loyalty_transactions(id) ON DELETE RESTRICT,
    coins integer NOT NULL CHECK (coins > 0),
    discount_amount numeric(14,2) NOT NULL CHECK (discount_amount > 0),
    status text NOT NULL DEFAULT 'redeemed' CHECK (status IN ('redeemed','restored')),
    created_at timestamptz NOT NULL DEFAULT now(),
    restored_at timestamptz
);
CREATE INDEX IF NOT EXISTS loyalty_order_redemptions_account_created_idx
    ON public.loyalty_order_redemptions (account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.loyalty_redemption_restorations (
    id bigserial PRIMARY KEY,
    order_redemption_id bigint NOT NULL REFERENCES public.loyalty_order_redemptions(id) ON DELETE RESTRICT,
    earned_transaction_id bigint NOT NULL REFERENCES public.loyalty_transactions(id) ON DELETE RESTRICT,
    restoration_transaction_id bigint NOT NULL UNIQUE REFERENCES public.loyalty_transactions(id) ON DELETE RESTRICT,
    coins integer NOT NULL CHECK (coins > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_redemption_id, earned_transaction_id)
);
CREATE INDEX IF NOT EXISTS loyalty_redemption_restorations_earned_idx
    ON public.loyalty_redemption_restorations (earned_transaction_id);

CREATE TABLE IF NOT EXISTS public.loyalty_expiration_allocations (
    id bigserial PRIMARY KEY,
    expiration_transaction_id bigint NOT NULL REFERENCES public.loyalty_transactions(id) ON DELETE RESTRICT,
    earned_transaction_id bigint NOT NULL REFERENCES public.loyalty_transactions(id) ON DELETE RESTRICT,
    coins integer NOT NULL CHECK (coins > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (expiration_transaction_id, earned_transaction_id)
);
CREATE INDEX IF NOT EXISTS loyalty_expiration_allocations_earned_idx
    ON public.loyalty_expiration_allocations (earned_transaction_id);

-- Dedicated Super Coins chart-of-account entries. Existing codes are never
-- renamed or retyped; fail safely if a code is already used with another type.
INSERT INTO public.accounting_accounts
    (code, name, account_type, sub_type, is_system, description)
VALUES
    ('2410', 'Super Coins Outstanding Liability', 'liability', 'current_liability', true,
     'Outstanding customer Super Coins redeemable for eligible purchases'),
    ('4210', 'Super Coins Breakage Income', 'income', 'other_income', false,
     'Finance-approved recognition of expired, unredeemed Super Coins'),
    ('6110', 'Super Coins Reward Expense', 'expense', 'operating', false,
     'Cost of Super Coins awarded to customers')
ON CONFLICT (code) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.accounting_accounts
        WHERE (code = '2410' AND account_type <> 'liability')
           OR (code = '4210' AND account_type <> 'income')
           OR (code = '6110' AND account_type <> 'expense')
    ) THEN
        RAISE EXCEPTION 'Super Coins account code already exists with an incompatible account type; review chart of accounts before applying migration 028';
    END IF;
END
$$;
