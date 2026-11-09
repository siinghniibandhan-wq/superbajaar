-- Advanced CRM support workspace.
-- Additive and idempotent. No customer/case backfill and no seeded SLA targets.
-- Repository sequence: 021 follows the 017-020 files reserved by the ERP integration branch.
-- The live schema_migrations ledger still requires owner preflight before production apply.

CREATE TABLE IF NOT EXISTS public.customer_account_customer_links (
    id bigserial PRIMARY KEY,
    customer_account_id bigint NOT NULL
        REFERENCES public.customer_accounts(id) ON DELETE RESTRICT,
    customer_id bigint NOT NULL
        REFERENCES public.customers(id) ON DELETE RESTRICT,
    linked_by_staff_user_id bigint
        REFERENCES public.app_users(id) ON DELETE SET NULL,
    verification_method text NOT NULL
        CHECK (verification_method IN ('email_otp', 'phone_otp', 'in_person', 'other')),
    verified_at timestamptz NOT NULL DEFAULT now(),
    linked_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT customer_account_customer_links_account_key UNIQUE (customer_account_id),
    CONSTRAINT customer_account_customer_links_customer_key UNIQUE (customer_id)
);

CREATE TABLE IF NOT EXISTS public.support_case_messages (
    id bigserial PRIMARY KEY,
    case_id bigint NOT NULL
        REFERENCES public.support_cases(id) ON DELETE RESTRICT,
    author_type text NOT NULL
        CHECK (author_type IN ('customer', 'staff', 'system')),
    author_customer_account_id bigint
        REFERENCES public.customer_accounts(id) ON DELETE RESTRICT,
    author_staff_user_id bigint
        REFERENCES public.app_users(id) ON DELETE RESTRICT,
    visibility text NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('public', 'internal')),
    body text NOT NULL
        CHECK (length(btrim(body)) BETWEEN 1 AND 10000),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT support_case_messages_author_check CHECK (
        (author_type = 'customer' AND author_customer_account_id IS NOT NULL AND author_staff_user_id IS NULL AND visibility = 'public')
        OR (author_type = 'staff' AND author_customer_account_id IS NULL AND author_staff_user_id IS NOT NULL)
        OR (author_type = 'system' AND author_customer_account_id IS NULL AND author_staff_user_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS support_case_messages_case_timeline_idx
    ON public.support_case_messages (case_id, created_at, id);
CREATE INDEX IF NOT EXISTS support_case_messages_public_timeline_idx
    ON public.support_case_messages (case_id, created_at, id)
    WHERE visibility = 'public';

CREATE TABLE IF NOT EXISTS public.support_case_events (
    id bigserial PRIMARY KEY,
    case_id bigint NOT NULL
        REFERENCES public.support_cases(id) ON DELETE RESTRICT,
    actor_type text NOT NULL
        CHECK (actor_type IN ('customer', 'staff', 'system')),
    actor_customer_account_id bigint
        REFERENCES public.customer_accounts(id) ON DELETE RESTRICT,
    actor_staff_user_id bigint
        REFERENCES public.app_users(id) ON DELETE RESTRICT,
    event_type text NOT NULL
        CHECK (length(btrim(event_type)) BETWEEN 1 AND 80),
    before_values jsonb,
    after_values jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT support_case_events_actor_check CHECK (
        (actor_type = 'customer' AND actor_customer_account_id IS NOT NULL AND actor_staff_user_id IS NULL)
        OR (actor_type = 'staff' AND actor_customer_account_id IS NULL AND actor_staff_user_id IS NOT NULL)
        OR (actor_type = 'system' AND actor_customer_account_id IS NULL AND actor_staff_user_id IS NULL)
    ),
    CONSTRAINT support_case_events_before_object_check
        CHECK (before_values IS NULL OR jsonb_typeof(before_values) = 'object'),
    CONSTRAINT support_case_events_after_object_check
        CHECK (after_values IS NULL OR jsonb_typeof(after_values) = 'object')
);

CREATE INDEX IF NOT EXISTS support_case_events_case_timeline_idx
    ON public.support_case_events (case_id, created_at, id);

CREATE TABLE IF NOT EXISTS public.support_sla_policies (
    id bigserial PRIMARY KEY,
    priority text NOT NULL
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    first_response_minutes integer NOT NULL
        CHECK (first_response_minutes > 0),
    resolution_minutes integer NOT NULL
        CHECK (resolution_minutes > 0),
    calendar_minutes boolean NOT NULL DEFAULT true,
    timezone text NOT NULL DEFAULT 'Asia/Kolkata',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS support_sla_policies_one_active_priority_idx
    ON public.support_sla_policies (priority)
    WHERE is_active = true;

ALTER TABLE public.support_cases
    ADD COLUMN IF NOT EXISTS sla_policy_id bigint
        REFERENCES public.support_sla_policies(id) ON DELETE RESTRICT;
ALTER TABLE public.support_cases
    ADD COLUMN IF NOT EXISTS first_response_due_at timestamptz;
ALTER TABLE public.support_cases
    ADD COLUMN IF NOT EXISTS resolution_due_at timestamptz;
ALTER TABLE public.support_cases
    ADD COLUMN IF NOT EXISTS first_response_at timestamptz;
ALTER TABLE public.support_cases
    ADD COLUMN IF NOT EXISTS resolved_at timestamptz;

CREATE INDEX IF NOT EXISTS support_cases_sla_queue_idx
    ON public.support_cases (status, resolution_due_at)
    WHERE status NOT IN ('resolved', 'closed');

CREATE OR REPLACE FUNCTION public.crm_prevent_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'CRM conversation and audit history is append-only'
        USING ERRCODE = '23514';
END
$$;

DO $crm_triggers$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'support_case_messages_append_only_trg'
          AND tgrelid = 'public.support_case_messages'::regclass
    ) THEN
        CREATE TRIGGER support_case_messages_append_only_trg
            BEFORE UPDATE OR DELETE ON public.support_case_messages
            FOR EACH ROW EXECUTE FUNCTION public.crm_prevent_audit_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'support_case_events_append_only_trg'
          AND tgrelid = 'public.support_case_events'::regclass
    ) THEN
        CREATE TRIGGER support_case_events_append_only_trg
            BEFORE UPDATE OR DELETE ON public.support_case_events
            FOR EACH ROW EXECUTE FUNCTION public.crm_prevent_audit_mutation();
    END IF;
END
$crm_triggers$;

-- Least-privilege application grants. No DELETE on account links, messages or events.
DO $crm_grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        GRANT SELECT, INSERT ON public.customer_account_customer_links TO superbajaar_user;
        GRANT SELECT, INSERT ON public.support_case_messages TO superbajaar_user;
        GRANT SELECT, INSERT ON public.support_case_events TO superbajaar_user;
        GRANT SELECT, INSERT, UPDATE ON public.support_sla_policies TO superbajaar_user;
        GRANT USAGE, SELECT ON SEQUENCE
            public.customer_account_customer_links_id_seq,
            public.support_case_messages_id_seq,
            public.support_case_events_id_seq,
            public.support_sla_policies_id_seq
            TO superbajaar_user;
    END IF;
END
$crm_grants$;
