-- Add the explicit Super Admin role without changing existing accounts.
-- Existing owner accounts remain valid for backwards compatibility.
ALTER TABLE public.app_users
    DROP CONSTRAINT IF EXISTS app_users_role_check;

ALTER TABLE public.app_users
    ADD CONSTRAINT app_users_role_check
    CHECK (role = ANY (ARRAY[
        'super_admin'::text,
        'owner'::text,
        'admin'::text,
        'manager'::text,
        'staff'::text,
        'viewer'::text
    ]));
