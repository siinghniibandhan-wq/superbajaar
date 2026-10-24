-- Historical selling-price snapshots for Super Bajaar variants.
-- Explicitly apply only when approved; this does not migrate products or integrate Odoo.
CREATE TABLE IF NOT EXISTS product_variant_price_history (
  id BIGSERIAL PRIMARY KEY,
  variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
  selling_price NUMERIC(12,2) NOT NULL CHECK (selling_price >= 0),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_variant_price_history_recent
  ON product_variant_price_history(variant_id, recorded_at DESC);

-- Capture a snapshot when an existing variant's selling price is inserted or changed.
CREATE OR REPLACE FUNCTION record_product_variant_selling_price()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.selling_price IS NOT NULL AND (
    TG_OP = 'INSERT' OR OLD.selling_price IS DISTINCT FROM NEW.selling_price
  ) THEN
    INSERT INTO product_variant_price_history(variant_id, selling_price)
    VALUES (NEW.id, NEW.selling_price);
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_record_product_variant_selling_price ON product_variants;
CREATE TRIGGER trg_record_product_variant_selling_price
AFTER INSERT OR UPDATE OF selling_price ON product_variants
FOR EACH ROW EXECUTE FUNCTION record_product_variant_selling_price();
