-- Add explicit cover-image selection without changing existing image references.
ALTER TABLE public.product_images
  ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;

-- Only one cover image is allowed per parent-product gallery or per variant gallery.
CREATE UNIQUE INDEX IF NOT EXISTS product_images_one_primary_per_gallery_idx
  ON public.product_images (product_id, COALESCE(variant_id, 0))
  WHERE is_primary = TRUE;
