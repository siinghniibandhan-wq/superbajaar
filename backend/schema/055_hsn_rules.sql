-- HSN/GST rules: category (and optional product-detail conditions) -> 8-digit HSN + GST rate.
-- Additive and idempotent. Rules point at categories by id, so renames never break them and a rule on a
-- parent category also covers sub-categories added later.
CREATE TABLE IF NOT EXISTS public.hsn_rules (
    id          BIGSERIAL PRIMARY KEY,
    category_id BIGINT REFERENCES public.categories(id) ON DELETE CASCADE,
    conditions  JSONB NOT NULL DEFAULT '{}'::jsonb,
    hsn_code    VARCHAR(8) NOT NULL,
    gst_rate    NUMERIC(5,2) NOT NULL,
    note        TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT hsn_rules_hsn_code_check CHECK (hsn_code ~ '^[0-9]{8}$'),
    CONSTRAINT hsn_rules_gst_rate_check CHECK (gst_rate >= 0 AND gst_rate <= 100),
    CONSTRAINT hsn_rules_conditions_check CHECK (jsonb_typeof(conditions) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hsn_rules_scope
    ON public.hsn_rules ((COALESCE(category_id, 0)), conditions) WHERE is_active;

CREATE INDEX IF NOT EXISTS ix_hsn_rules_category ON public.hsn_rules (category_id);

DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.hsn_rules TO superbajaar_user';
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE public.hsn_rules_id_seq TO superbajaar_user';
    END IF;
END
$grant$;
