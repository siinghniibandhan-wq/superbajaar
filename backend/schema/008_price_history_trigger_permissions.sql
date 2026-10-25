-- Allow the price-history trigger to record price changes when the API role
-- can update product_variants but does not have direct INSERT on the history table.
-- The function owner must be the schema-migration role that owns the history table.
CREATE OR REPLACE FUNCTION record_product_variant_selling_price()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF NEW.selling_price IS NOT NULL AND (
    TG_OP = 'INSERT' OR OLD.selling_price IS DISTINCT FROM NEW.selling_price
  ) THEN
    INSERT INTO public.product_variant_price_history(variant_id, selling_price)
    VALUES (NEW.id, NEW.selling_price);
  END IF;
  RETURN NEW;
END;
$$;
