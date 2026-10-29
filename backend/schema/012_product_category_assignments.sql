-- Support assigning a product to multiple categories without duplicating the product.
-- Idempotent additive migration; preserves the existing products.category_id as the primary category.
CREATE TABLE IF NOT EXISTS public.product_category_assignments (
    product_id bigint NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    category_id bigint NOT NULL REFERENCES public.categories(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, category_id)
);

-- Backfill each existing product's primary category into the assignment table.
INSERT INTO public.product_category_assignments (product_id, category_id)
SELECT p.id, p.category_id
FROM public.products p
WHERE p.category_id IS NOT NULL
ON CONFLICT (product_id, category_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS product_category_assignments_category_idx
    ON public.product_category_assignments (category_id, product_id);
