-- 023: configurable operational-to-accounting mappings and posting exceptions.
-- Additive and idempotent. No existing ledger rows or migration files are changed.

CREATE TABLE IF NOT EXISTS public.accounting_event_account_mappings (
    id bigserial PRIMARY KEY,
    legal_entity_code varchar(32) NOT NULL DEFAULT 'DEFAULT',
    source_module varchar(40) NOT NULL,
    event_type varchar(80) NOT NULL,
    line_role varchar(80) NOT NULL,
    account_id bigint NOT NULL REFERENCES public.accounting_accounts(id) ON DELETE RESTRICT,
    tax_component text,
    cost_centre varchar(80),
    effective_from date NOT NULL,
    effective_to date,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','in_review','approved','rejected','superseded')),
    source_reference text,
    notes text,
    created_by_user_id bigint,
    submitted_by_user_id bigint,
    approved_by_user_id bigint,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounting_event_mapping_period_check
        CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CONSTRAINT accounting_event_mapping_component_check
        CHECK (tax_component IS NULL OR tax_component IN ('cgst','sgst','igst'))
);

CREATE INDEX IF NOT EXISTS accounting_event_mappings_lookup_idx
    ON public.accounting_event_account_mappings
       (legal_entity_code,source_module,event_type,line_role,effective_from)
    WHERE status='approved';

CREATE TABLE IF NOT EXISTS public.accounting_posting_exceptions (
    id bigserial PRIMARY KEY,
    source_module varchar(40) NOT NULL,
    source_type varchar(80) NOT NULL,
    source_id varchar(100) NOT NULL,
    event_key varchar(120) NOT NULL,
    event_date date NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','exception','posted','resolved','ignored')),
    exception_code varchar(80),
    exception_message text,
    voucher_id bigint REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_attempt_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounting_posting_exception_source_event_uq
        UNIQUE (source_module,source_type,source_id,event_key)
);

CREATE INDEX IF NOT EXISTS accounting_posting_exceptions_queue_idx
    ON public.accounting_posting_exceptions(status,source_module,event_date,created_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT,INSERT,UPDATE ON public.accounting_event_account_mappings,
            public.accounting_posting_exceptions TO superbajaar_user;
        GRANT USAGE,SELECT ON SEQUENCE public.accounting_event_account_mappings_id_seq,
            public.accounting_posting_exceptions_id_seq TO superbajaar_user;
    END IF;
END $$;
