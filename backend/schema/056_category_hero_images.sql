-- Admin-managed hero slider images for each storefront category page.
-- A category may have any number of images; they play in sort_order on the website.
CREATE TABLE IF NOT EXISTS public.category_hero_images (
    id          BIGSERIAL PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES public.categories(id) ON DELETE CASCADE,
    image_url   TEXT NOT NULL CHECK (length(btrim(image_url)) > 0),
    alt_text    TEXT CHECK (alt_text IS NULL OR length(alt_text) <= 300),
    sort_order  INTEGER NOT NULL DEFAULT 0 CHECK (sort_order BETWEEN 0 AND 10000),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_category_hero_images_category_order
    ON public.category_hero_images (category_id, sort_order, id);
