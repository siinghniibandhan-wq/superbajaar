-- 080: durable, idempotent provider refund records (supports partial refunds).
CREATE TABLE IF NOT EXISTS public.payment_refunds (
    id BIGSERIAL PRIMARY KEY,
    payment_id BIGINT NOT NULL REFERENCES public.payments(id) ON DELETE RESTRICT,
    order_id BIGINT NOT NULL REFERENCES public.orders(id) ON DELETE RESTRICT,
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'INR' CHECK (currency='INR'),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processed','failed')),
    provider VARCHAR(30) NOT NULL DEFAULT 'razorpay',
    provider_refund_id VARCHAR(120),
    idempotency_key VARCHAR(120) NOT NULL UNIQUE,
    note TEXT,
    created_by_user_id BIGINT REFERENCES public.app_users(id) ON DELETE SET NULL,
    created_by_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (provider_refund_id IS NULL OR length(provider_refund_id) > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS payment_refunds_provider_id_uq
    ON public.payment_refunds(provider,provider_refund_id)
    WHERE provider_refund_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS payment_refunds_payment_idx
    ON public.payment_refunds(payment_id,created_at);
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT,INSERT,UPDATE ON public.payment_refunds TO superbajaar_user;
        GRANT USAGE,SELECT ON SEQUENCE public.payment_refunds_id_seq TO superbajaar_user;
    END IF;
END
$grant$;
