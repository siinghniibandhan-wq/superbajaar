-- Selling price history per variant, used for "Lowest price in last 30 days".
-- A trigger records every price change, so no application code path can miss one.
CREATE TABLE IF NOT EXISTS variant_price_history (
    id BIGSERIAL PRIMARY KEY,
    variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    selling_price NUMERIC(12,2) NOT NULL CHECK (selling_price >= 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_variant_price_history_lookup
    ON variant_price_history(variant_id, recorded_at DESC);

CREATE OR REPLACE FUNCTION record_variant_price_history() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.selling_price IS DISTINCT FROM OLD.selling_price THEN
        INSERT INTO variant_price_history (variant_id, selling_price, recorded_at)
        VALUES (NEW.id, NEW.selling_price, now());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_variant_price_history ON product_variants;
CREATE TRIGGER trg_variant_price_history
    AFTER INSERT OR UPDATE OF selling_price ON product_variants
    FOR EACH ROW EXECUTE FUNCTION record_variant_price_history();

-- Start tracking from today for variants that already exist (no earlier data is available).
INSERT INTO variant_price_history (variant_id, selling_price, recorded_at)
SELECT v.id, v.selling_price, now()
FROM product_variants v
WHERE NOT EXISTS (SELECT 1 FROM variant_price_history h WHERE h.variant_id = v.id);
