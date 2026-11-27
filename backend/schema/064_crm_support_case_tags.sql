-- CRM support-case tags.
-- Additive and idempotent. Existing cases and CRM history are unchanged.

CREATE TABLE IF NOT EXISTS public.tags (
    id bigserial PRIMARY KEY,
    name text NOT NULL UNIQUE
        CHECK (length(btrim(name)) BETWEEN 1 AND 50),
    color text NOT NULL DEFAULT '#607d8b'
        CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS tags_name_ci_idx
    ON public.tags (lower(name));

CREATE TABLE IF NOT EXISTS public.support_case_tags (
    case_id bigint NOT NULL
        REFERENCES public.support_cases(id) ON DELETE CASCADE,
    tag_id bigint NOT NULL
        REFERENCES public.tags(id) ON DELETE CASCADE,
    PRIMARY KEY (case_id, tag_id)
);

CREATE INDEX IF NOT EXISTS support_case_tags_tag_idx
    ON public.support_case_tags (tag_id);

-- Grant only the operations used by the CRM API, and only when the role exists.
DO $crm_tag_grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        GRANT SELECT, INSERT ON public.tags TO superbajaar_user;
        GRANT SELECT, INSERT, DELETE ON public.support_case_tags TO superbajaar_user;
        GRANT USAGE, SELECT ON SEQUENCE public.tags_id_seq TO superbajaar_user;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_app') THEN
        GRANT SELECT, INSERT ON public.tags TO superbajaar_app;
        GRANT SELECT, INSERT, DELETE ON public.support_case_tags TO superbajaar_app;
        GRANT USAGE, SELECT ON SEQUENCE public.tags_id_seq TO superbajaar_app;
    END IF;
END
$crm_tag_grants$;
