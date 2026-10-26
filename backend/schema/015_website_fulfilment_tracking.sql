-- Additive website fulfilment metadata; existing orders and shipments are preserved.
ALTER TABLE sb_shipments ADD COLUMN IF NOT EXISTS tracking_url TEXT;
ALTER TABLE sb_shipments ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS sb_shipments_website_order_idx ON sb_shipments(order_type, order_id, created_at DESC);
