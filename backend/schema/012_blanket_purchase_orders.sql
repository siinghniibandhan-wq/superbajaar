-- Blanket purchase agreements and release orders.
CREATE TABLE IF NOT EXISTS sb_blanket_orders (
  id BIGSERIAL PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','closed','cancelled','expired')),
  valid_from DATE NOT NULL,
  valid_until DATE NOT NULL,
  max_value NUMERIC(14,2) NOT NULL CHECK (max_value > 0),
  items JSONB NOT NULL,
  created_by BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (valid_until >= valid_from)
);
CREATE TABLE IF NOT EXISTS sb_blanket_releases (
  id BIGSERIAL PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  blanket_order_id BIGINT NOT NULL REFERENCES sb_blanket_orders(id),
  status TEXT NOT NULL DEFAULT 'released' CHECK (status IN ('released','cancelled','received','closed')),
  items JSONB NOT NULL,
  total_value NUMERIC(14,2) NOT NULL CHECK (total_value >= 0),
  created_by BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sb_blanket_orders_status_idx ON sb_blanket_orders(status, valid_until);
CREATE INDEX IF NOT EXISTS sb_blanket_releases_order_idx ON sb_blanket_releases(blanket_order_id, status, created_at);
