-- Add product tags without changing existing catalogue records.
-- The foreign key intentionally uses the default NO ACTION behavior so deleting
-- a product cannot automatically cascade-delete tag records.

CREATE TABLE IF NOT EXISTS public.product_tags (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT REFERENCES public.products(id),
    tag TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_product_tags_product_id
    ON public.product_tags (product_id);
