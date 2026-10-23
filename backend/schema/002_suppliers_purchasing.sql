-- Super Bajaar supplier and purchasing foundation (PostgreSQL)
-- Apply only after reviewing against the selected database and existing Odoo model.
CREATE TABLE IF NOT EXISTS suppliers (
  id BIGSERIAL PRIMARY KEY,
  supplier_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  legal_name TEXT,
  gstin TEXT,
  email TEXT,
  phone TEXT,
  billing_address JSONB NOT NULL DEFAULT '{}'::jsonb,
  shipping_address JSONB NOT NULL DEFAULT '{}'::jsonb,
  payment_terms_days INTEGER NOT NULL DEFAULT 0 CHECK (payment_terms_days >= 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','blocked')),
  source_system TEXT,
  source_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS supplier_products (
  id BIGSERIAL PRIMARY KEY,
  supplier_id BIGINT NOT NULL REFERENCES suppliers(id),
  product_variant_id BIGINT NOT NULL,
  supplier_sku TEXT,
  purchase_price NUMERIC(14,2) CHECK (purchase_price >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  minimum_order_quantity NUMERIC(14,3) NOT NULL DEFAULT 1 CHECK (minimum_order_quantity > 0),
  lead_time_days INTEGER CHECK (lead_time_days >= 0),
  is_preferred BOOLEAN NOT NULL DEFAULT false,
  valid_from DATE,
  valid_to DATE,
  UNIQUE (supplier_id, product_variant_id, valid_from)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  id BIGSERIAL PRIMARY KEY,
  purchase_order_number TEXT NOT NULL UNIQUE,
  supplier_id BIGINT NOT NULL REFERENCES suppliers(id),
  warehouse_id BIGINT NOT NULL,
  order_date DATE NOT NULL,
  expected_date DATE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','part_received','received','cancelled','closed')),
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  subtotal NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
  tax_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
  grand_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (grand_total >= 0),
  source_system TEXT,
  source_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_record_id)
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
  id BIGSERIAL PRIMARY KEY,
  purchase_order_id BIGINT NOT NULL REFERENCES purchase_orders(id) ON DELETE RESTRICT,
  line_number INTEGER NOT NULL CHECK (line_number > 0),
  product_variant_id BIGINT NOT NULL,
  ordered_quantity NUMERIC(14,3) NOT NULL CHECK (ordered_quantity > 0),
  received_quantity NUMERIC(14,3) NOT NULL DEFAULT 0 CHECK (received_quantity >= 0 AND received_quantity <= ordered_quantity),
  unit_cost NUMERIC(14,2) NOT NULL CHECK (unit_cost >= 0),
  discount_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
  tax_rate NUMERIC(6,3) NOT NULL DEFAULT 0 CHECK (tax_rate >= 0),
  line_total NUMERIC(14,2) NOT NULL CHECK (line_total >= 0),
  UNIQUE (purchase_order_id, line_number)
);
