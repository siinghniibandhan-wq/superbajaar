-- Additive website fulfilment metadata; create the operational shipment table when absent.
CREATE TABLE IF NOT EXISTS sb_shipments (
    id BIGSERIAL PRIMARY KEY,
    order_type TEXT NOT NULL,
    order_id BIGINT NOT NULL,
    carrier TEXT,
    tracking_number TEXT,
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created','packed','in_transit','out_for_delivery','delivered','exception','cancelled')),
    estimated_delivery DATE,
    delivered_at TIMESTAMPTZ,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE sb_shipments ADD COLUMN IF NOT EXISTS tracking_url TEXT;
ALTER TABLE sb_shipments ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS sb_shipments_website_order_idx ON sb_shipments(order_type, order_id, created_at DESC);
