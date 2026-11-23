-- Customer-facing attribute display styles.
-- Replaces the dropdown presentation with selectable controls (pill, circle, tile, swatch, thumbnail).
-- Idempotent: safe to re-run. Existing attribute definitions and saved values are retained.
ALTER TABLE public.product_attributes DROP CONSTRAINT IF EXISTS product_attributes_display_type_check;

-- Move every legacy dropdown definition to the default selector for its attribute type.
UPDATE public.product_attributes
SET display_type = CASE value_type
        WHEN 'colour' THEN 'colour'
        WHEN 'image'  THEN 'image'
        ELSE 'button'
    END
WHERE display_type = 'dropdown';

ALTER TABLE public.product_attributes ALTER COLUMN display_type SET DEFAULT 'button';

ALTER TABLE public.product_attributes
    ADD CONSTRAINT product_attributes_display_type_check
    CHECK (display_type IN ('text', 'button', 'circle', 'tile', 'colour', 'colour_chip', 'image', 'image_circle'));
