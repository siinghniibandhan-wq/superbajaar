-- Additive product delivery availability foundation; preserves existing catalogue IDs.
ALTER TABLE products ADD COLUMN IF NOT EXISTS tax_category TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS gst_rate NUMERIC(5,2) NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN IF NOT EXISTS tax_inclusive BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS sale_badge TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS sale_badge_active BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS sb_regions (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sb_region_pincodes (
    id BIGSERIAL PRIMARY KEY,
    region_id BIGINT NOT NULL REFERENCES sb_regions(id) ON DELETE CASCADE,
    pincode TEXT NOT NULL CHECK (pincode ~ '^[0-9]{6}$'),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(region_id, pincode)
);
CREATE INDEX IF NOT EXISTS sb_region_pincodes_pin_idx ON sb_region_pincodes(pincode);

CREATE TABLE IF NOT EXISTS sb_product_availability_rules (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_id BIGINT REFERENCES product_variants(id) ON DELETE CASCADE,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('region','pincode','warehouse')),
    region_id BIGINT REFERENCES sb_regions(id) ON DELETE CASCADE,
    pincode TEXT CHECK (pincode IS NULL OR pincode ~ '^[0-9]{6}$'),
    warehouse_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
      (scope_type='region' AND region_id IS NOT NULL AND pincode IS NULL AND warehouse_id IS NULL) OR
      (scope_type='pincode' AND pincode IS NOT NULL AND region_id IS NULL AND warehouse_id IS NULL) OR
      (scope_type='warehouse' AND warehouse_id IS NOT NULL AND region_id IS NULL AND pincode IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS sb_product_availability_lookup_idx
    ON sb_product_availability_rules(product_id, variant_id, scope_type);

ALTER TABLE sb_warehouses ADD COLUMN IF NOT EXISTS region_id BIGINT REFERENCES sb_regions(id) ON DELETE SET NULL;
