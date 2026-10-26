-- Additive inventory transfer workflow. Apply through the existing numbered-schema deployment process.
CREATE TABLE IF NOT EXISTS sb_inventory_transfers (
  id BIGSERIAL PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  source_warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id),
  destination_warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','in_transit','partially_received','received','cancelled')),
  items JSONB NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_by BIGINT,
  dispatched_by BIGINT,
  received_by BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  dispatched_at TIMESTAMPTZ,
  received_at TIMESTAMPTZ,
  CHECK (source_warehouse_id <> destination_warehouse_id)
);
CREATE TABLE IF NOT EXISTS sb_inventory_transfer_events (
  id BIGSERIAL PRIMARY KEY,
  transfer_id BIGINT NOT NULL REFERENCES sb_inventory_transfers(id),
  transfer_reference TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor_id BIGINT,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sb_inventory_transfer_status_idx ON sb_inventory_transfers(status,created_at DESC);
CREATE INDEX IF NOT EXISTS sb_inventory_transfer_events_ref_idx ON sb_inventory_transfer_events(transfer_reference,created_at);
