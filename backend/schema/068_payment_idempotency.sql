-- 068: Idempotency identity for standalone payment creation.
-- Existing payment rows remain valid; new API-created rows carry a unique key and payload hash.
ALTER TABLE public.payments
    ADD COLUMN IF NOT EXISTS idempotency_key varchar(120),
    ADD COLUMN IF NOT EXISTS idempotency_payload_sha256 char(64);
CREATE UNIQUE INDEX IF NOT EXISTS payments_idempotency_key_uidx
    ON public.payments(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_app') THEN
        GRANT SELECT, INSERT, UPDATE ON public.payments TO superbajaar_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT, INSERT, UPDATE ON public.payments TO superbajaar_user;
    END IF;
END
$grant$;
