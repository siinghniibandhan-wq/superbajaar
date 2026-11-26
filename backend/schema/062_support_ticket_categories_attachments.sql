-- Support tickets: subject categories and customer file attachments.
-- Additive and idempotent. Legacy tickets keep category NULL.
-- Depends on 021_crm_support_workspace.sql (support_case_messages, crm_prevent_audit_mutation).

ALTER TABLE public.support_cases
    ADD COLUMN IF NOT EXISTS category text;

DO $support_category$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'support_cases_category_check'
          AND conrelid = 'public.support_cases'::regclass
    ) THEN
        ALTER TABLE public.support_cases
            ADD CONSTRAINT support_cases_category_check
            CHECK (category IS NULL OR category IN (
                'item_not_listed',
                'account_issue',
                'supercoin',
                'order_delayed',
                'cancellation_refund',
                'payment_issue',
                'referral_earning',
                'feedback'
            ));
    END IF;
END
$support_category$;

CREATE INDEX IF NOT EXISTS support_cases_category_idx
    ON public.support_cases (category, created_at DESC)
    WHERE category IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.support_case_attachments (
    id bigserial PRIMARY KEY,
    case_id bigint NOT NULL
        REFERENCES public.support_cases(id) ON DELETE RESTRICT,
    message_id bigint
        REFERENCES public.support_case_messages(id) ON DELETE RESTRICT,
    uploaded_by_customer_account_id bigint NOT NULL
        REFERENCES public.customer_accounts(id) ON DELETE RESTRICT,
    object_key text NOT NULL,
    original_filename text NOT NULL
        CHECK (length(btrim(original_filename)) BETWEEN 1 AND 255),
    content_type text NOT NULL
        CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')),
    file_size_bytes integer NOT NULL
        CHECK (file_size_bytes BETWEEN 1 AND 5242880),
    sha256_hex text NOT NULL
        CHECK (sha256_hex ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT support_case_attachments_object_key_key UNIQUE (object_key)
);

CREATE INDEX IF NOT EXISTS support_case_attachments_case_idx
    ON public.support_case_attachments (case_id, created_at, id);

DO $support_attachment_trigger$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'support_case_attachments_append_only_trg'
          AND tgrelid = 'public.support_case_attachments'::regclass
    ) THEN
        CREATE TRIGGER support_case_attachments_append_only_trg
            BEFORE UPDATE OR DELETE ON public.support_case_attachments
            FOR EACH ROW EXECUTE FUNCTION public.crm_prevent_audit_mutation();
    END IF;
END
$support_attachment_trigger$;

DO $support_attachment_grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        GRANT SELECT, INSERT ON public.support_case_attachments TO superbajaar_user;
        GRANT USAGE, SELECT ON SEQUENCE public.support_case_attachments_id_seq TO superbajaar_user;
    END IF;
END
$support_attachment_grants$;
