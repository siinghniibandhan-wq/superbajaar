-- CRM enhancements: Tagging system.
-- Additive.

CREATE TABLE IF NOT EXISTS public.tags (
    id bigserial PRIMARY KEY,
    name text NOT NULL UNIQUE,
    color text NOT NULL DEFAULT '#607d8b',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.support_case_tags (
    case_id bigint NOT NULL
        REFERENCES public.support_cases(id) ON DELETE CASCADE,
    tag_id bigint NOT NULL
        REFERENCES public.tags(id) ON DELETE CASCADE,
    PRIMARY KEY (case_id, tag_id)
);

CREATE INDEX IF NOT EXISTS support_case_tags_tag_idx ON public.support_case_tags (tag_id);

GRANT SELECT, INSERT, DELETE ON public.tags TO superbajaar_user;
GRANT SELECT, INSERT, DELETE ON public.support_case_tags TO superbajaar_user;
GRANT USAGE, SELECT ON SEQUENCE public.tags_id_seq TO superbajaar_user;
