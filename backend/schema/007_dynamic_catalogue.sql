-- Dynamic catalogue hierarchy, configurable variant presentation, product details and galleries.
-- Existing categories remain top-level unless a parent is selected.
CREATE TABLE IF NOT EXISTS catalog_attributes (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  values_json JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE product_categories ADD COLUMN IF NOT EXISTS parent_id BIGINT NULL REFERENCES product_categories(id) ON DELETE SET NULL;
ALTER TABLE catalog_attributes ADD COLUMN IF NOT EXISTS display_type TEXT NOT NULL DEFAULT 'text' CHECK (display_type IN ('text','color','image','dropdown','button'));
CREATE TABLE IF NOT EXISTS product_variant_images (
  id BIGSERIAL PRIMARY KEY,
  variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL,
  alt_text TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS product_variant_images_variant_sort_idx ON product_variant_images(variant_id, sort_order, id);
ALTER TABLE products ADD COLUMN IF NOT EXISTS specifications JSONB NOT NULL DEFAULT '[]', ADD COLUMN IF NOT EXISTS manufacturer_details JSONB NOT NULL DEFAULT '[]', ADD COLUMN IF NOT EXISTS seller_details JSONB NOT NULL DEFAULT '[]';
CREATE INDEX IF NOT EXISTS product_categories_parent_idx ON product_categories(parent_id);
