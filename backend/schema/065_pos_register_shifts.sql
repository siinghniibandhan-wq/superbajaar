-- POS registers, independent cashier shifts and auditable cash drawer controls.
CREATE TABLE IF NOT EXISTS public.pos_registers (
    id bigserial PRIMARY KEY,
    location_id bigint NOT NULL REFERENCES public.stock_locations(id) ON DELETE RESTRICT,
    register_code varchar(40) NOT NULL,
    name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_by bigint REFERENCES public.app_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (location_id, register_code)
);

CREATE TABLE IF NOT EXISTS public.pos_register_shifts (
    id bigserial PRIMARY KEY,
    register_id bigint NOT NULL REFERENCES public.pos_registers(id) ON DELETE RESTRICT,
    cashier_user_id bigint NOT NULL REFERENCES public.app_users(id) ON DELETE RESTRICT,
    opened_by bigint NOT NULL REFERENCES public.app_users(id) ON DELETE RESTRICT,
    opening_float numeric(14,2) NOT NULL CHECK (opening_float >= 0),
    opened_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    expected_cash numeric(14,2),
    counted_cash numeric(14,2),
    cash_variance numeric(14,2),
    closing_note text,
    closed_by bigint REFERENCES public.app_users(id) ON DELETE RESTRICT,
    closed_at timestamptz,
    CHECK (
      (status='open' AND counted_cash IS NULL AND closed_at IS NULL)
      OR
      (status='closed' AND counted_cash IS NOT NULL AND expected_cash IS NOT NULL AND cash_variance IS NOT NULL AND closed_at IS NOT NULL AND closed_by IS NOT NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_one_open_shift_per_register
    ON public.pos_register_shifts(register_id) WHERE status='open';
CREATE INDEX IF NOT EXISTS idx_pos_shifts_cashier_opened
    ON public.pos_register_shifts(cashier_user_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS public.pos_cash_movements (
    id bigserial PRIMARY KEY,
    shift_id bigint NOT NULL REFERENCES public.pos_register_shifts(id) ON DELETE RESTRICT,
    movement_type text NOT NULL CHECK (movement_type IN ('cash_in','cash_out')),
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    reason text NOT NULL CHECK (length(trim(reason)) >= 3),
    reference text,
    created_by bigint NOT NULL REFERENCES public.app_users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pos_cash_movements_shift
    ON public.pos_cash_movements(shift_id, created_at, id);

CREATE TABLE IF NOT EXISTS public.pos_register_audit (
    id bigserial PRIMARY KEY,
    register_id bigint REFERENCES public.pos_registers(id) ON DELETE RESTRICT,
    shift_id bigint REFERENCES public.pos_register_shifts(id) ON DELETE RESTRICT,
    event_type text NOT NULL,
    actor_user_id bigint REFERENCES public.app_users(id) ON DELETE SET NULL,
    event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pos_register_audit_shift
    ON public.pos_register_audit(shift_id, created_at DESC);

-- POS permissions are intentionally scoped: cashiers can operate shifts; managers can configure registers.
INSERT INTO public.app_role_permissions (role_id,module_id,permission_id,allowed)
SELECT r.id,m.id,p.id,true
FROM public.app_roles r
JOIN public.app_modules m ON m.module_key='pos'
JOIN public.app_permissions p ON
    (r.name IN ('staff','manager') AND p.action_key IN ('read','create','edit'))
    OR (r.name IN ('manager','admin') AND p.action_key IN ('approve','configure','export'))
WHERE r.name IN ('staff','manager','admin')
ON CONFLICT (role_id,module_id,permission_id) DO UPDATE SET allowed=true;

ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS pos_register_shift_id bigint REFERENCES public.pos_register_shifts(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_orders_pos_register_shift ON public.orders(pos_register_shift_id) WHERE pos_register_shift_id IS NOT NULL;
