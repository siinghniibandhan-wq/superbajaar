-- Allow "Image" attributes.
-- The baseline CHECK on product_attributes.value_type never listed 'image', so saving an Image
-- attribute failed with "The value violates a catalogue validation rule" (check violation 23514).
-- Idempotent: safe to re-run. Existing attribute definitions and values are untouched.
ALTER TABLE public.product_attributes DROP CONSTRAINT IF EXISTS product_attributes_value_type_check;

ALTER TABLE public.product_attributes
    ADD CONSTRAINT product_attributes_value_type_check
    CHECK (value_type IN ('text','number','boolean','date','select','multi_select','colour','size','image'));
