-- 065: Social sign-in (Google, GitHub) for customer accounts.
-- Additive and idempotent. Existing customer_accounts rows are not modified.
CREATE TABLE IF NOT EXISTS public.customer_oauth_identities (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES public.customer_accounts(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('google','github')),
    provider_user_id TEXT NOT NULL,
    provider_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    UNIQUE (provider, provider_user_id),
    UNIQUE (customer_id, provider)
);
CREATE INDEX IF NOT EXISTS customer_oauth_identities_customer_idx
    ON public.customer_oauth_identities (customer_id);
