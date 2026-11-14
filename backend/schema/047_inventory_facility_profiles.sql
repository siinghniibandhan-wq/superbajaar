-- 047: additive, one-to-one operational profiles for existing stock facilities.
-- stock_locations remains the canonical facility identity; no stock rows are moved.
CREATE TABLE IF NOT EXISTS public.stock_location_profiles (
    location_id bigint PRIMARY KEY REFERENCES public.stock_locations(id) ON DELETE RESTRICT,
    facility_code varchar(40) NOT NULL UNIQUE,
    profile_data jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT stock_location_profiles_code_nonblank CHECK (length(trim(facility_code)) >= 2),
    CONSTRAINT stock_location_profiles_data_object CHECK (jsonb_typeof(profile_data) = 'object')
);
CREATE INDEX IF NOT EXISTS stock_location_profiles_data_gin_idx
    ON public.stock_location_profiles USING gin(profile_data);
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT, INSERT, UPDATE ON public.stock_location_profiles TO superbajaar_user;
    END IF;
END
$grant$;
