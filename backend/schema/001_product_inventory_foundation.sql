-- Super Bajaar product and inventory foundation (PostgreSQL).
-- Review foreign keys and naming against the chosen production database before applying.
CREATE TABLE IF NOT EXISTS product_categories (
  id BIGSERIAL PRIMARY KEY,
  category_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  parent_id BIGINT REFERENCES product_categories(id),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  source_system TEXT,
  source_record_id TEXT,
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS products (
  id BIGSERIAL PRIMARY KEY,
  product_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  brand TEXT,
  category_id BIGINT REFERENCES product_categories(id),
  product_type TEXT NOT NULL DEFAULT 'goods',
  hsn_code TEXT,
  tax_rate NUMERIC(6,3) CHECK (tax_rate IS NULL OR tax_rate >= 0),
  unit_of_measure TEXT NOT NULL DEFAULT 'unit',
  website_published BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','inactive','archived')),
  source_system TEXT,
  source_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS product_variants (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  sku TEXT NOT NULL UNIQUE,
  barcode TEXT UNIQUE,
  variant_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
  mrp NUMERIC(14,2) CHECK (mrp IS NULL OR mrp >= 0),
  selling_price NUMERIC(14,2) CHECK (selling_price IS NULL OR selling_price >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  weight NUMERIC(12,3) CHECK (weight IS NULL OR weight >= 0),
  track_inventory BOOLEAN NOT NULL DEFAULT true,
  batch_tracking BOOLEAN NOT NULL DEFAULT false,
  expiry_tracking BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  source_system TEXT,
  source_record_id TEXT,
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS warehouses (
  id BIGSERIAL PRIMARY KEY,
  warehouse_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  address JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  source_system TEXT,
  source_record_id TEXT,
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS inventory_balances (
  id BIGSERIAL PRIMARY KEY,
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(id),
  product_variant_id BIGINT NOT NULL REFERENCES product_variants(id),
  quantity_on_hand NUMERIC(14,3) NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
  quantity_reserved NUMERIC(14,3) NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0 AND quantity_reserved <= quantity_on_hand),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (warehouse_id, product_variant_id)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
  id BIGSERIAL PRIMARY KEY,
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(id),
  product_variant_id BIGINT NOT NULL REFERENCES product_variants(id),
  movement_type TEXT NOT NULL CHECK (movement_type IN ('opening','receipt','sale','return','transfer_in','transfer_out','adjustment','damage')),
  quantity_delta NUMERIC(14,3) NOT NULL CHECK (quantity_delta <> 0),
  unit_cost NUMERIC(14,2) CHECK (unit_cost IS NULL OR unit_cost >= 0),
  reference_type TEXT,
  reference_id TEXT,
  movement_at TIMESTAMPTZ NOT NULL,
  source_system TEXT,
  source_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS product_price_history (
  id BIGSERIAL PRIMARY KEY,
  product_variant_id BIGINT NOT NULL REFERENCES product_variants(id),
  price_type TEXT NOT NULL CHECK (price_type IN ('mrp','selling','offer')),
  price NUMERIC(14,2) NOT NULL CHECK (price >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  reason TEXT,
  source_system TEXT,
  source_record_id TEXT,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  UNIQUE (source_system, source_record_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_variant_date ON inventory_movements(product_variant_id, movement_at);
CREATE INDEX IF NOT EXISTS idx_price_history_variant_date ON product_price_history(product_variant_id, valid_from DESC);
