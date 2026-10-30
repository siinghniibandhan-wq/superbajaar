-- Add a storefront presentation mode to product attributes.
-- Idempotent and non-destructive: existing definitions and values are retained.
ALTER TABLE public.product_attributes
    ADD COLUMN IF NOT EXISTS display_type text NOT NULL DEFAULT 'dropdown';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'product_attributes_display_type_check'
          AND conrelid = 'public.product_attributes'::regclass
    ) THEN
        ALTER TABLE public.product_attributes
            ADD CONSTRAINT product_attributes_display_type_check
            CHECK (display_type IN ('text', 'dropdown', 'button', 'colour', 'image'));
    END IF;
END
$$;

-- Give existing Colour attributes the matching storefront presentation by default.
UPDATE public.product_attributes
SET display_type = 'colour'
WHERE value_type = 'colour' AND display_type = 'dropdown';
