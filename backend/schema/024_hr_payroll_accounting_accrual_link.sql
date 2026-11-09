-- 024: link payroll accrual journals separately from net-pay settlement vouchers.
-- The existing accounting_voucher_id remains the bank/payment voucher reference.

ALTER TABLE public.hr_payroll_runs
    ADD COLUMN IF NOT EXISTS accounting_accrual_voucher_id bigint
    REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX IF NOT EXISTS hr_payroll_runs_accrual_voucher_uidx
    ON public.hr_payroll_runs(accounting_accrual_voucher_id)
    WHERE accounting_accrual_voucher_id IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
        GRANT SELECT,UPDATE ON public.hr_payroll_runs TO superbajaar_user;
    END IF;
END $$;
