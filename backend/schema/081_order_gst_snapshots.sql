-- 081: immutable GST calculation snapshots for omnichannel order lines.
ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS tax_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    ADD COLUMN IF NOT EXISTS place_of_supply_state TEXT;
ALTER TABLE public.order_lines
    ADD COLUMN IF NOT EXISTS gst_rule_id BIGINT REFERENCES public.hsn_rules(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS hsn_code VARCHAR(8),
    ADD COLUMN IF NOT EXISTS gst_rate NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (gst_rate >= 0 AND gst_rate <= 100),
    ADD COLUMN IF NOT EXISTS taxable_value NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (taxable_value >= 0),
    ADD COLUMN IF NOT EXISTS cgst_rate NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (cgst_rate >= 0),
    ADD COLUMN IF NOT EXISTS sgst_rate NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (sgst_rate >= 0),
    ADD COLUMN IF NOT EXISTS igst_rate NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (igst_rate >= 0),
    ADD COLUMN IF NOT EXISTS cgst_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (cgst_amount >= 0),
    ADD COLUMN IF NOT EXISTS sgst_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (sgst_amount >= 0),
    ADD COLUMN IF NOT EXISTS igst_amount NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (igst_amount >= 0),
    ADD COLUMN IF NOT EXISTS tax_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0);
ALTER TABLE public.order_lines
    DROP CONSTRAINT IF EXISTS order_lines_hsn_code_check;
ALTER TABLE public.order_lines
    ADD CONSTRAINT order_lines_hsn_code_check
    CHECK (hsn_code IS NULL OR hsn_code ~ '^[0-9]{8}$');
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT,UPDATE ON public.orders,public.order_lines TO superbajaar_user;
    END IF;
END
$grant$;
