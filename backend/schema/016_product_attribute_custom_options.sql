-- Add product-scoped selectable options without changing shared attribute definitions.
-- Additive and idempotent. Existing product/variant data is preserved.
-- The application role grant is conditional so clean CI databases without that role can validate the migration.

CREATE TABLE IF NOT EXISTS product_attribute_custom_options (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attribute_id BIGINT NOT NULL REFERENCES product_attributes(id) ON DELETE CASCADE,
    value JSONB NOT NULL,
    option_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT product_attribute_custom_options_nonempty_key CHECK (length(btrim(option_key)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_attribute_custom_options_scope_key
    ON product_attribute_custom_options (product_id, attribute_id, option_key);

CREATE INDEX IF NOT EXISTS ix_product_attribute_custom_options_attribute
    ON product_attribute_custom_options (attribute_id, product_id);

DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE product_attribute_custom_options TO superbajaar_user';
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE product_attribute_custom_options_id_seq TO superbajaar_user';
    END IF;
END
$grant$;
