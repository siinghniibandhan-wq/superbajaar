-- 082: transactional promotion/coupon rules and order redemption snapshots.
ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS discount_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (discount_total >= 0),
    ADD COLUMN IF NOT EXISTS promotion_code VARCHAR(40);

CREATE TABLE IF NOT EXISTS public.promotions (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(160) NOT NULL,
    discount_type VARCHAR(12) NOT NULL CHECK (discount_type IN ('percent','fixed')),
    discount_value NUMERIC(14,2) NOT NULL CHECK (discount_value > 0),
    minimum_subtotal NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (minimum_subtotal >= 0),
    maximum_discount NUMERIC(14,2) CHECK (maximum_discount IS NULL OR maximum_discount > 0),
    usage_limit INTEGER CHECK (usage_limit IS NULL OR usage_limit > 0),
    per_customer_limit INTEGER CHECK (per_customer_limit IS NULL OR per_customer_limit > 0),
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id BIGINT REFERENCES public.app_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (discount_type <> 'percent' OR discount_value <= 100),
    CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at),
    CHECK (maximum_discount IS NULL OR discount_type='percent')
);
CREATE UNIQUE INDEX IF NOT EXISTS promotions_code_uq ON public.promotions (upper(code));
CREATE INDEX IF NOT EXISTS promotions_active_window_idx ON public.promotions(is_active, starts_at, ends_at);

CREATE TABLE IF NOT EXISTS public.promotion_redemptions (
    id BIGSERIAL PRIMARY KEY,
    promotion_id BIGINT NOT NULL REFERENCES public.promotions(id) ON DELETE RESTRICT,
    order_id BIGINT NOT NULL UNIQUE REFERENCES public.orders(id) ON DELETE RESTRICT,
    customer_email TEXT,
    customer_phone TEXT,
    subtotal NUMERIC(14,2) NOT NULL CHECK (subtotal >= 0),
    discount_amount NUMERIC(14,2) NOT NULL CHECK (discount_amount > 0),
    code_snapshot VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS promotion_redemptions_promotion_idx ON public.promotion_redemptions(promotion_id, created_at);
CREATE INDEX IF NOT EXISTS promotion_redemptions_customer_email_idx ON public.promotion_redemptions(promotion_id, lower(customer_email)) WHERE customer_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS promotion_redemptions_customer_phone_idx ON public.promotion_redemptions(promotion_id, customer_phone) WHERE customer_phone IS NOT NULL;

DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT,INSERT,UPDATE ON public.promotions,public.promotion_redemptions TO superbajaar_user;
        GRANT USAGE,SELECT ON SEQUENCE public.promotions_id_seq,public.promotion_redemptions_id_seq TO superbajaar_user;
    END IF;
END
$grant$;
