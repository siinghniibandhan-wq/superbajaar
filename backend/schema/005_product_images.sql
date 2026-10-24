-- Product image URL stored on each product variant. Existing records remain valid.
ALTER TABLE product_variants
  ADD COLUMN IF NOT EXISTS image_url TEXT;

COMMENT ON COLUMN product_variants.image_url IS 'Public HTTP(S) URL for the product variant image';
