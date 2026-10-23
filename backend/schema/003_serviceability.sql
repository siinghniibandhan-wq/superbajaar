-- PIN-code coverage is maintained by authorized operations/admin workflows.
-- Do not enable customer-facing availability until coverage data has been verified.
CREATE TABLE IF NOT EXISTS warehouse_serviceability (
  id BIGSERIAL PRIMARY KEY,
  warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
  pincode CHAR(6) NOT NULL CHECK (pincode ~ '^[0-9]{6}$'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_to TIMESTAMPTZ,
  source_system TEXT,
  source_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  UNIQUE (warehouse_id, pincode, valid_from),
  UNIQUE (source_system, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_warehouse_serviceability_pin_status
  ON warehouse_serviceability(pincode, status);
