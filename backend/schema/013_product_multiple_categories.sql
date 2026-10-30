-- Keep the multi-category API aligned with the existing 012 migration.
-- 012_product_category_assignments.sql already owns this association table.
-- This additive, idempotent guard does not create a parallel category table.
CREATE TABLE IF NOT EXISTS public.product_category_assignments (
    product_id bigint NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    category_id bigint NOT NULL REFERENCES public.categories(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, category_id)
);

CREATE INDEX IF NOT EXISTS product_category_assignments_category_idx
    ON public.product_category_assignments (category_id, product_id);

INSERT INTO public.product_category_assignments (product_id, category_id)
SELECT p.id, p.category_id
FROM public.products p
WHERE p.category_id IS NOT NULL
ON CONFLICT (product_id, category_id) DO NOTHING;
