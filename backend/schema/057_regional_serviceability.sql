-- Regional serviceability: State -> District -> PIN coverage per warehouse (standard + express),
-- an India PIN directory cache, and the delivery type chosen on each order.
-- Idempotent and additive.

CREATE TABLE IF NOT EXISTS public.india_pin_directory (
    pin_code   CHAR(6) PRIMARY KEY CHECK (pin_code ~ '^[1-9][0-9]{5}$'),
    state      TEXT NOT NULL CHECK (length(btrim(state)) > 0),
    district   TEXT,
    office     TEXT,
    source     TEXT NOT NULL DEFAULT 'import',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_india_pin_directory_state_district
    ON public.india_pin_directory (lower(state), lower(district));

ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS delivery_type TEXT NOT NULL DEFAULT 'standard';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'orders_delivery_type_check') THEN
        ALTER TABLE public.orders ADD CONSTRAINT orders_delivery_type_check CHECK (delivery_type IN ('standard', 'express'));
    END IF;
END $$;

-- Existing warehouses: the old behaviour auto-filled "service_pin_codes" with the warehouse's own PIN.
-- Under the new rule an empty PIN list means "serve the whole selected area", so convert those
-- auto-filled entries into State coverage. Warehouses with a deliberate PIN list are left untouched.
UPDATE public.stock_location_profiles p
SET profile_data = (profile_data
        || jsonb_build_object('service_states', jsonb_build_array(profile_data->>'state'))
        || jsonb_build_object('service_pin_codes', '[]'::jsonb)),
    updated_at = now()
FROM public.stock_locations sl
WHERE sl.id = p.location_id
  AND profile_data ? 'state'
  AND NOT (profile_data ? 'service_states')
  AND (profile_data->'service_pin_codes' IS NULL
       OR profile_data->'service_pin_codes' = jsonb_build_array(sl.pin_code)
       OR jsonb_array_length(profile_data->'service_pin_codes') = 0);
