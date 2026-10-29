-- Allow a product to appear in multiple storefront and catalogue categories.
-- Keep products.category_id as the legacy/default category for existing integrations.
CREATE TABLE IF NOT EXISTS public.product_categories (
  product_id BIGINT NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
  category_id BIGINT NOT NULL REFERENCES public.categories(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (product_id, category_id)
);

CREATE INDEX IF NOT EXISTS product_categories_category_product_idx
  ON public.product_categories (category_id, product_id);

INSERT INTO public.product_categories (product_id, category_id)
SELECT id, category_id FROM public.products WHERE category_id IS NOT NULL
ON CONFLICT DO NOTHING;
