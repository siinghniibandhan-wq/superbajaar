-- Admin-managed hero slider images for the storefront homepage.
-- Any number of images; they play in sort_order on the website home page.
CREATE TABLE IF NOT EXISTS public.homepage_hero_images (
    id          BIGSERIAL PRIMARY KEY,
    image_url   TEXT NOT NULL CHECK (length(btrim(image_url)) > 0),
    alt_text    TEXT CHECK (alt_text IS NULL OR length(alt_text) <= 300),
    sort_order  INTEGER NOT NULL DEFAULT 0 CHECK (sort_order BETWEEN 0 AND 10000),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_homepage_hero_images_order
    ON public.homepage_hero_images (sort_order, id);
