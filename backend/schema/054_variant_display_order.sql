-- Admin-controlled display order for a product's variants (e.g. 0.1 Kg, 0.250 Kg, 0.5 Kg, 1 Kg).
-- Additive and idempotent. Existing variants keep sort_order 0, so they still fall back to SKU order
-- until someone reorders them.
ALTER TABLE public.product_variants ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_product_variants_product_sort
    ON public.product_variants (product_id, sort_order, sku);
