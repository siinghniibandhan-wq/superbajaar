-- Configurable RBAC: roles, modules, actions and user-specific module grants.
-- Additive migration. Existing owner accounts are downgraded to admin; Super Admin remains the only top-level authority.
CREATE TABLE IF NOT EXISTS public.app_roles (
    id bigserial PRIMARY KEY,
    name varchar(60) NOT NULL UNIQUE,
    label varchar(100) NOT NULL,
    is_system boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.app_modules (
    id bigserial PRIMARY KEY,
    module_key varchar(80) NOT NULL UNIQUE,
    label varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS public.app_permissions (
    id bigserial PRIMARY KEY,
    action_key varchar(40) NOT NULL UNIQUE,
    label varchar(80) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.app_role_permissions (
    role_id bigint NOT NULL REFERENCES public.app_roles(id) ON DELETE CASCADE,
    module_id bigint NOT NULL REFERENCES public.app_modules(id) ON DELETE CASCADE,
    permission_id bigint NOT NULL REFERENCES public.app_permissions(id) ON DELETE CASCADE,
    allowed boolean NOT NULL DEFAULT false,
    PRIMARY KEY (role_id, module_id, permission_id)
);

CREATE TABLE IF NOT EXISTS public.app_user_module_permissions (
    user_id bigint NOT NULL REFERENCES public.app_users(id) ON DELETE CASCADE,
    module_id bigint NOT NULL REFERENCES public.app_modules(id) ON DELETE CASCADE,
    permission_id bigint NOT NULL REFERENCES public.app_permissions(id) ON DELETE CASCADE,
    allowed boolean NOT NULL DEFAULT false,
    updated_by_user_id bigint REFERENCES public.app_users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, module_id, permission_id)
);

INSERT INTO public.app_roles (name, label) VALUES
    ('super_admin', 'Super Admin'),
    ('admin', 'Admin'),
    ('manager', 'Manager'),
    ('staff', 'Staff'),
    ('viewer', 'Viewer')
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.app_modules (module_key, label) VALUES
    ('catalogue', 'Catalogue'),
    ('inventory', 'Inventory'),
    ('purchasing', 'Purchasing'),
    ('pos', 'POS'),
    ('crm', 'CRM'),
    ('orders', 'Orders'),
    ('payments', 'Payments'),
    ('fulfillment', 'Fulfillment'),
    ('delivery', 'Delivery'),
    ('pricing', 'Pricing'),
    ('loyalty', 'Loyalty'),
    ('hr_payroll', 'HR & Payroll'),
    ('accounting', 'Accounting'),
    ('dashboard', 'Master Dashboard'),
    ('user_management', 'User Management')
ON CONFLICT (module_key) DO NOTHING;

INSERT INTO public.app_permissions (action_key, label) VALUES
    ('read', 'Read'),
    ('create', 'Create'),
    ('edit', 'Edit'),
    ('delete', 'Delete'),
    ('approve', 'Approve'),
    ('export', 'Export'),
    ('configure', 'Configure')
ON CONFLICT (action_key) DO NOTHING;

-- Preserve legacy access during rollout, while removing the obsolete owner role.
UPDATE public.app_users SET role = 'admin', updated_at = now() WHERE role = 'owner';

-- Default grants are only starting templates. User-specific assignments can narrow or extend
-- them, subject to the assigning administrator's own effective authority.
INSERT INTO public.app_role_permissions (role_id, module_id, permission_id, allowed)
SELECT r.id, m.id, p.id, (r.name = 'super_admin')
FROM public.app_roles r
CROSS JOIN public.app_modules m
CROSS JOIN public.app_permissions p
ON CONFLICT (role_id, module_id, permission_id) DO NOTHING;

-- Seed non-super-admin defaults conservatively. They are editable in the permission manager.
INSERT INTO public.app_role_permissions (role_id, module_id, permission_id, allowed)
SELECT r.id, m.id, p.id, true
FROM public.app_roles r
JOIN public.app_modules m ON (
    (r.name = 'admin') OR
    (r.name = 'manager' AND m.module_key IN ('inventory','purchasing','orders','payments','delivery','crm','hr_payroll')) OR
    (r.name = 'staff' AND m.module_key IN ('orders','delivery','crm')) OR
    (r.name = 'viewer')
)
JOIN public.app_permissions p ON p.action_key = 'read'
WHERE r.name <> 'super_admin'
ON CONFLICT (role_id, module_id, permission_id) DO UPDATE SET allowed = EXCLUDED.allowed;

-- Admin receives operational write permissions by default, but not user/role administration.
INSERT INTO public.app_role_permissions (role_id, module_id, permission_id, allowed)
SELECT r.id, m.id, p.id, true
FROM public.app_roles r
JOIN public.app_modules m ON (r.name = 'admin' OR (r.name = 'manager' AND m.module_key IN ('inventory','purchasing','orders','payments','delivery','crm','hr_payroll')))
JOIN public.app_permissions p ON p.action_key IN ('create','edit','approve','export')
WHERE r.name <> 'super_admin'
ON CONFLICT (role_id, module_id, permission_id) DO UPDATE SET allowed = EXCLUDED.allowed;

-- User and role administration is a separate protected module.
INSERT INTO public.app_role_permissions (role_id, module_id, permission_id, allowed)
SELECT r.id, m.id, p.id, (r.name IN ('super_admin','admin'))
FROM public.app_roles r
JOIN public.app_modules m ON m.module_key = 'user_management'
JOIN public.app_permissions p ON p.action_key IN ('read','create','edit')
ON CONFLICT (role_id, module_id, permission_id) DO UPDATE SET allowed = EXCLUDED.allowed;
