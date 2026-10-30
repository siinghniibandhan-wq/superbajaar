-- Keep a durable record of product deletions and the operator's mandatory reason.
-- Deliberately no FK to products or app_users: audit history must survive deletion.
CREATE TABLE IF NOT EXISTS public.product_deletion_audit (
    id bigserial PRIMARY KEY,
    product_id bigint NOT NULL,
    product_name varchar(240) NOT NULL,
    product_slug varchar(260) NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) >= 10),
    deleted_by_user_id bigint NOT NULL,
    deleted_by_email varchar(254) NOT NULL,
    deleted_by_role varchar(20) NOT NULL CHECK (deleted_by_role IN ('owner', 'admin')),
    deleted_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS product_deletion_audit_product_idx
    ON public.product_deletion_audit (product_id, deleted_at DESC);

-- Grant only the access required by the application role when it exists.
-- Disposable CI databases do not create the production application role.
SELECT 'GRANT SELECT, INSERT ON public.product_deletion_audit TO superbajaar_user'
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') \gexec
SELECT 'GRANT USAGE, SELECT ON SEQUENCE public.product_deletion_audit_id_seq TO superbajaar_user'
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') \gexec
