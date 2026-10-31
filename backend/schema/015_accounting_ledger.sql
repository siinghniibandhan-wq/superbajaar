-- Accounting & Tax: double-entry general ledger, vouchers, GST tax lines,
-- bank reconciliation, period lock and voucher numbering.
--
-- Additive and idempotent: every object uses IF NOT EXISTS / ON CONFLICT DO NOTHING,
-- functions use CREATE OR REPLACE and triggers are created only when missing.
-- No existing table is altered. Posted accounting records cannot be deleted and
-- their amounts cannot be edited; corrections are made with reversal vouchers.

-- 1. Business-level accounting settings (single row, id = 1).
CREATE TABLE IF NOT EXISTS public.accounting_settings (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    business_name text NOT NULL DEFAULT 'Super Bajaar',
    gstin character(15),
    state_code character(2),
    default_supply text NOT NULL DEFAULT 'intra' CHECK (default_supply IN ('intra', 'inter')),
    lock_date date,
    updated_by_email text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounting_settings_state_code_check CHECK (state_code IS NULL OR state_code ~ '^[0-9]{2}$')
);

INSERT INTO public.accounting_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 2. Chart of accounts.
CREATE TABLE IF NOT EXISTS public.accounting_accounts (
    id bigserial PRIMARY KEY,
    code varchar(20) NOT NULL UNIQUE,
    name varchar(160) NOT NULL CHECK (length(btrim(name)) > 0),
    account_type text NOT NULL CHECK (account_type IN ('asset', 'liability', 'equity', 'income', 'expense')),
    sub_type text NOT NULL DEFAULT 'general',
    parent_id bigint REFERENCES public.accounting_accounts(id) ON DELETE RESTRICT,
    description text,
    is_system boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounting_accounts_code_check CHECK (code ~ '^[0-9A-Z][0-9A-Z-]{0,19}$')
);

CREATE INDEX IF NOT EXISTS accounting_accounts_type_idx
    ON public.accounting_accounts (account_type, sub_type);

-- 3. Voucher numbering per voucher type and Indian financial year (April-March).
CREATE TABLE IF NOT EXISTS public.accounting_voucher_sequences (
    voucher_type text NOT NULL,
    fiscal_year varchar(7) NOT NULL,
    last_number integer NOT NULL DEFAULT 0 CHECK (last_number >= 0),
    PRIMARY KEY (voucher_type, fiscal_year)
);

-- 4. Voucher (journal entry) header.
CREATE TABLE IF NOT EXISTS public.accounting_vouchers (
    id bigserial PRIMARY KEY,
    voucher_number varchar(40) NOT NULL UNIQUE,
    voucher_type text NOT NULL CHECK (voucher_type IN (
        'journal', 'sales', 'purchase', 'receipt', 'payment', 'contra', 'expense',
        'credit_note', 'debit_note', 'opening', 'reversal'
    )),
    voucher_date date NOT NULL,
    status text NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'reversed')),
    narration text,
    reference varchar(100),
    party_type text CHECK (party_type IS NULL OR party_type IN ('customer', 'supplier', 'employee', 'other')),
    party_name varchar(200),
    party_gstin character(15),
    place_of_supply text CHECK (place_of_supply IS NULL OR place_of_supply IN ('intra', 'inter')),
    due_date date,
    taxable_total numeric(16,2) NOT NULL DEFAULT 0 CHECK (taxable_total >= 0),
    tax_total numeric(16,2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    total_amount numeric(16,2) NOT NULL CHECK (total_amount > 0),
    source_type text,
    source_id varchar(80),
    idempotency_key varchar(100) UNIQUE,
    reversal_of_id bigint REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT,
    reversed_by_voucher_id bigint REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT,
    reversal_reason text,
    reversed_at timestamptz,
    reversed_by_email varchar(254),
    created_by_user_id bigint,
    created_by_email varchar(254),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounting_vouchers_source_pair_check CHECK ((source_type IS NULL) = (source_id IS NULL)),
    CONSTRAINT accounting_vouchers_due_date_check CHECK (due_date IS NULL OR due_date >= voucher_date)
);

-- One automatic posting per operational source record (orders, payments, receipts).
CREATE UNIQUE INDEX IF NOT EXISTS accounting_vouchers_source_uidx
    ON public.accounting_vouchers (source_type, source_id) WHERE source_type IS NOT NULL;
-- A voucher can be reversed only once.
CREATE UNIQUE INDEX IF NOT EXISTS accounting_vouchers_reversal_uidx
    ON public.accounting_vouchers (reversal_of_id) WHERE reversal_of_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS accounting_vouchers_date_idx
    ON public.accounting_vouchers (voucher_date, id);
CREATE INDEX IF NOT EXISTS accounting_vouchers_party_idx
    ON public.accounting_vouchers (party_name) WHERE party_name IS NOT NULL;

-- 5. Voucher lines (ledger postings).
CREATE TABLE IF NOT EXISTS public.accounting_voucher_lines (
    id bigserial PRIMARY KEY,
    voucher_id bigint NOT NULL REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT,
    line_no integer NOT NULL CHECK (line_no > 0),
    account_id bigint NOT NULL REFERENCES public.accounting_accounts(id) ON DELETE RESTRICT,
    debit numeric(16,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
    credit numeric(16,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
    narration varchar(300),
    hsn_sac varchar(8),
    quantity numeric(14,3),
    unit_rate numeric(14,2),
    gst_rate numeric(5,2) CHECK (gst_rate IS NULL OR (gst_rate >= 0 AND gst_rate <= 100)),
    tax_component text CHECK (tax_component IS NULL OR tax_component IN ('cgst', 'sgst', 'igst')),
    reconciled_on date,
    bank_reference varchar(100),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounting_voucher_lines_one_side_check CHECK ((debit > 0) <> (credit > 0)),
    CONSTRAINT accounting_voucher_lines_voucher_line_key UNIQUE (voucher_id, line_no)
);

CREATE INDEX IF NOT EXISTS accounting_voucher_lines_account_idx
    ON public.accounting_voucher_lines (account_id, voucher_id);

-- 6. Integrity: every voucher must balance (total debit = total credit) and have
--    at least two lines. Checked at commit so header and lines insert together.
CREATE OR REPLACE FUNCTION public.accounting_check_voucher_balance() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    target_id bigint;
    line_count integer;
    total_debit numeric;
    total_credit numeric;
BEGIN
    IF TG_TABLE_NAME = 'accounting_vouchers' THEN
        target_id := NEW.id;
    ELSE
        target_id := NEW.voucher_id;
    END IF;
    SELECT count(*), COALESCE(sum(debit), 0), COALESCE(sum(credit), 0)
      INTO line_count, total_debit, total_credit
      FROM public.accounting_voucher_lines WHERE voucher_id = target_id;
    IF line_count < 2 THEN
        RAISE EXCEPTION 'Accounting voucher % must have at least two lines', target_id
            USING ERRCODE = '23514';
    END IF;
    IF total_debit <> total_credit THEN
        RAISE EXCEPTION 'Accounting voucher % is not balanced (debit %, credit %)', target_id, total_debit, total_credit
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END
$$;

-- 7. Immutability: posted ledger records are never deleted; amounts/accounts are
--    never edited. Only reversal metadata and bank reconciliation fields may change.
CREATE OR REPLACE FUNCTION public.accounting_protect_records() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Posted accounting records cannot be deleted; post a reversal instead'
            USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'accounting_voucher_lines' THEN
        IF NEW.voucher_id IS DISTINCT FROM OLD.voucher_id
           OR NEW.line_no IS DISTINCT FROM OLD.line_no
           OR NEW.account_id IS DISTINCT FROM OLD.account_id
           OR NEW.debit IS DISTINCT FROM OLD.debit
           OR NEW.credit IS DISTINCT FROM OLD.credit
           OR NEW.gst_rate IS DISTINCT FROM OLD.gst_rate
           OR NEW.tax_component IS DISTINCT FROM OLD.tax_component THEN
            RAISE EXCEPTION 'Posted accounting lines cannot be changed; post a reversal instead'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        IF NEW.voucher_number IS DISTINCT FROM OLD.voucher_number
           OR NEW.voucher_type IS DISTINCT FROM OLD.voucher_type
           OR NEW.voucher_date IS DISTINCT FROM OLD.voucher_date
           OR NEW.total_amount IS DISTINCT FROM OLD.total_amount
           OR NEW.taxable_total IS DISTINCT FROM OLD.taxable_total
           OR NEW.tax_total IS DISTINCT FROM OLD.tax_total
           OR NEW.source_type IS DISTINCT FROM OLD.source_type
           OR NEW.source_id IS DISTINCT FROM OLD.source_id
           OR NEW.reversal_of_id IS DISTINCT FROM OLD.reversal_of_id
           OR (OLD.status = 'reversed' AND NEW.status <> 'reversed') THEN
            RAISE EXCEPTION 'Posted accounting vouchers cannot be changed; post a reversal instead'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'accounting_voucher_lines_balance_trg'
                   AND tgrelid = 'public.accounting_voucher_lines'::regclass) THEN
        CREATE CONSTRAINT TRIGGER accounting_voucher_lines_balance_trg
            AFTER INSERT OR UPDATE ON public.accounting_voucher_lines
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.accounting_check_voucher_balance();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'accounting_vouchers_balance_trg'
                   AND tgrelid = 'public.accounting_vouchers'::regclass) THEN
        CREATE CONSTRAINT TRIGGER accounting_vouchers_balance_trg
            AFTER INSERT ON public.accounting_vouchers
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.accounting_check_voucher_balance();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'accounting_voucher_lines_protect_trg'
                   AND tgrelid = 'public.accounting_voucher_lines'::regclass) THEN
        CREATE TRIGGER accounting_voucher_lines_protect_trg
            BEFORE UPDATE OR DELETE ON public.accounting_voucher_lines
            FOR EACH ROW EXECUTE FUNCTION public.accounting_protect_records();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'accounting_vouchers_protect_trg'
                   AND tgrelid = 'public.accounting_vouchers'::regclass) THEN
        CREATE TRIGGER accounting_vouchers_protect_trg
            BEFORE UPDATE OR DELETE ON public.accounting_vouchers
            FOR EACH ROW EXECUTE FUNCTION public.accounting_protect_records();
    END IF;
END
$$;

-- 8. Default chart of accounts for an Indian retail / e-commerce business.
--    System accounts are used by automatic postings and cannot be retyped or deactivated.
INSERT INTO public.accounting_accounts (code, name, account_type, sub_type, is_system, description) VALUES
    ('1000', 'Cash in hand', 'asset', 'cash', true, 'Store cash and COD collections'),
    ('1010', 'Bank account', 'asset', 'bank', true, 'Primary business current account'),
    ('1020', 'UPI and wallet clearing', 'asset', 'bank', true, 'UPI and wallet collections awaiting settlement'),
    ('1030', 'Card settlement clearing', 'asset', 'bank', true, 'Card collections awaiting settlement'),
    ('1100', 'Accounts receivable', 'asset', 'receivable', true, 'Amounts due from customers'),
    ('1200', 'Inventory - stock in hand', 'asset', 'inventory', true, 'Stock valued at cost'),
    ('1300', 'Input CGST', 'asset', 'tax_input', true, 'CGST paid on purchases (input tax credit)'),
    ('1301', 'Input SGST', 'asset', 'tax_input', true, 'SGST paid on purchases (input tax credit)'),
    ('1302', 'Input IGST', 'asset', 'tax_input', true, 'IGST paid on purchases (input tax credit)'),
    ('1400', 'Advances and deposits', 'asset', 'current_asset', false, 'Supplier advances, rent and security deposits'),
    ('1500', 'Furniture and equipment', 'asset', 'fixed_asset', false, 'Store fixtures, computers and equipment'),
    ('2000', 'Accounts payable', 'liability', 'payable', true, 'Amounts due to suppliers'),
    ('2050', 'Goods received not invoiced', 'liability', 'payable', true, 'Stock received against purchase orders awaiting supplier bill'),
    ('2100', 'Output CGST', 'liability', 'tax_output', true, 'CGST collected on sales'),
    ('2101', 'Output SGST', 'liability', 'tax_output', true, 'SGST collected on sales'),
    ('2102', 'Output IGST', 'liability', 'tax_output', true, 'IGST collected on sales'),
    ('2200', 'TDS payable', 'liability', 'statutory', false, 'Tax deducted at source awaiting deposit'),
    ('2300', 'Salaries payable', 'liability', 'current_liability', false, 'Salaries due to employees'),
    ('2400', 'Customer advances', 'liability', 'current_liability', false, 'Payments received before delivery'),
    ('2500', 'Loans', 'liability', 'loan', false, 'Business loans and borrowings'),
    ('3000', 'Owner''s capital', 'equity', 'capital', true, 'Capital introduced by the owner'),
    ('3100', 'Owner''s drawings', 'equity', 'drawings', false, 'Withdrawals by the owner'),
    ('3200', 'Retained earnings', 'equity', 'retained_earnings', true, 'Accumulated profits of earlier years'),
    ('3900', 'Opening balance adjustment', 'equity', 'opening', true, 'Balancing account for opening balances'),
    ('4000', 'Sales - goods', 'income', 'sales', true, 'Revenue from sale of goods'),
    ('4010', 'Sales returns', 'income', 'sales_return', true, 'Goods returned by customers (credit notes)'),
    ('4100', 'Delivery and other charges', 'income', 'other_income', true, 'Delivery, packing and other charges recovered'),
    ('4200', 'Other income', 'income', 'other_income', false, 'Interest, commission and miscellaneous income'),
    ('4300', 'Discount received', 'income', 'other_income', false, 'Discounts received from suppliers'),
    ('4900', 'Round off', 'income', 'other_income', true, 'Invoice rounding differences'),
    ('5000', 'Cost of goods sold', 'expense', 'cogs', true, 'Cost of stock sold'),
    ('5010', 'Purchases - non-stock', 'expense', 'cogs', false, 'Direct purchases not held as inventory'),
    ('5100', 'Discount allowed', 'expense', 'direct', true, 'Discounts given to customers'),
    ('6000', 'Rent', 'expense', 'operating', false, NULL),
    ('6010', 'Salaries and wages', 'expense', 'operating', false, NULL),
    ('6020', 'Electricity and utilities', 'expense', 'operating', false, NULL),
    ('6030', 'Transport and delivery', 'expense', 'operating', false, NULL),
    ('6040', 'Packaging materials', 'expense', 'operating', false, NULL),
    ('6050', 'Marketing and advertising', 'expense', 'operating', false, NULL),
    ('6060', 'Bank and payment gateway charges', 'expense', 'operating', false, NULL),
    ('6070', 'Office and general expenses', 'expense', 'operating', false, NULL),
    ('6080', 'Repairs and maintenance', 'expense', 'operating', false, NULL),
    ('6090', 'Telephone and internet', 'expense', 'operating', false, NULL),
    ('6100', 'Professional fees', 'expense', 'operating', false, NULL),
    ('6900', 'Miscellaneous expenses', 'expense', 'operating', false, NULL)
ON CONFLICT (code) DO NOTHING;

-- 9. Least-privilege grants for the application role when it exists.
--    No DELETE is granted: ledger records are corrected with reversals only.
--    Disposable CI databases do not create the production application role.
SELECT 'GRANT SELECT, INSERT, UPDATE ON public.accounting_settings, public.accounting_accounts, public.accounting_voucher_sequences, public.accounting_vouchers, public.accounting_voucher_lines TO superbajaar_user'
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') \gexec
SELECT 'GRANT USAGE, SELECT ON SEQUENCE public.accounting_accounts_id_seq, public.accounting_vouchers_id_seq, public.accounting_voucher_lines_id_seq TO superbajaar_user'
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') \gexec
