-- Product creation foundation: tax assignment, sale badges and hierarchical availability.
-- Additive and idempotent. Existing product/variant records are preserved.
ALTER TABLE products ADD COLUMN IF NOT EXISTS tax_category TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS gst_rate NUMERIC(5,2);
ALTER TABLE products ADD COLUMN IF NOT EXISTS sale_badge TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN IF NOT EXISTS sale_badge_active BOOLEAN NOT NULL DEFAULT FALSE;

-- Region registry supports grouping PIN codes and warehouses without hardcoding cities in UI.
CREATE TABLE IF NOT EXISTS sb_regions (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL UNIQUE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sb_region_pincodes (
  region_id BIGINT NOT NULL REFERENCES sb_regions(id) ON DELETE CASCADE,
  pincode TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY(region_id, pincode),
  CHECK (pincode ~ '^[0-9]{6}$')
);

-- Connect existing warehouses to regions; a warehouse can serve multiple PIN codes.
ALTER TABLE sb_warehouses ADD COLUMN IF NOT EXISTS region_id BIGINT REFERENCES sb_regions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS sb_warehouses_region_idx ON sb_warehouses(region_id) WHERE active = TRUE;

-- No rows means unrestricted availability. Once rules exist, matching restrictions are
-- combined: selected region, PIN code and/or warehouse must all match.
CREATE TABLE IF NOT EXISTS sb_product_availability_rules (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  variant_id BIGINT REFERENCES product_variants(id) ON DELETE CASCADE,
  scope_type TEXT NOT NULL CHECK (scope_type IN ('region','pincode','warehouse')),
  region_id BIGINT REFERENCES sb_regions(id) ON DELETE CASCADE,
  pincode TEXT,
  warehouse_id BIGINT REFERENCES sb_warehouses(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (scope_type = 'region' AND region_id IS NOT NULL AND pincode IS NULL AND warehouse_id IS NULL) OR
    (scope_type = 'pincode' AND pincode IS NOT NULL AND region_id IS NULL AND warehouse_id IS NULL AND pincode ~ '^[0-9]{6}$') OR
    (scope_type = 'warehouse' AND warehouse_id IS NOT NULL AND region_id IS NULL AND pincode IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS sb_product_availability_product_idx
  ON sb_product_availability_rules(product_id, variant_id);
CREATE INDEX IF NOT EXISTS sb_product_availability_region_idx
  ON sb_product_availability_rules(region_id, pincode);

-- Tax options remain sourced from the existing accounting/tax configuration. This table
-- stores the selected tax identity/rate for a product; it does not duplicate the tax engine.
CREATE TABLE IF NOT EXISTS sb_product_tax_assignments (
  product_id BIGINT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
  tax_category TEXT NOT NULL,
  gst_rate NUMERIC(5,2) NOT NULL CHECK (gst_rate >= 0 AND gst_rate <= 100),
  hsn_code TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
