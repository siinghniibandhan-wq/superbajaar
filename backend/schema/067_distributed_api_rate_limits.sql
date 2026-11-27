-- 067: Distributed API rate-limit buckets.
-- PostgreSQL is the shared atomic store across all API workers/EC2 instances.
CREATE TABLE IF NOT EXISTS public.api_rate_limit_buckets (
    bucket_key char(64) PRIMARY KEY,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS api_rate_limit_buckets_updated_idx
    ON public.api_rate_limit_buckets(updated_at);
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.api_rate_limit_buckets TO superbajaar_app;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.api_rate_limit_buckets TO superbajaar_user;
    END IF;
END
$grant$;
