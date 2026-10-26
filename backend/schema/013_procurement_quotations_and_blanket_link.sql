-- Multiple supplier quotations and blanket-release linkage for the procurement lifecycle.
CREATE TABLE IF NOT EXISTS sb_supplier_quotations (
  id BIGSERIAL PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  procurement_id BIGINT NOT NULL REFERENCES sb_procurements(id) ON DELETE CASCADE,
  vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
  status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','selected','rejected')),
  items JSONB NOT NULL,
  total_value NUMERIC(14,2) NOT NULL CHECK (total_value >= 0),
  submitted_by BIGINT,
  selected_by BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sb_supplier_quotations_procurement ON sb_supplier_quotations(procurement_id, created_at DESC);
ALTER TABLE sb_blanket_releases ADD COLUMN IF NOT EXISTS procurement_id BIGINT REFERENCES sb_procurements(id);
