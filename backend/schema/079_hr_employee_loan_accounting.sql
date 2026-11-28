-- 079: double-entry accounting linkage for employee loan disbursements and repayments.
ALTER TABLE public.hr_employee_loans
 ADD COLUMN IF NOT EXISTS disbursement_voucher_id bigint REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT,
 ADD COLUMN IF NOT EXISTS disbursed_by_user_id bigint REFERENCES public.app_users(id) ON DELETE SET NULL,
 ADD COLUMN IF NOT EXISTS disbursed_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS hr_employee_loans_disbursement_voucher_uq
 ON public.hr_employee_loans(disbursement_voucher_id) WHERE disbursement_voucher_id IS NOT NULL;
ALTER TABLE public.hr_employee_loan_transactions
 ADD COLUMN IF NOT EXISTS accounting_voucher_id bigint REFERENCES public.accounting_vouchers(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS hr_employee_loan_transactions_accounting_voucher_uq
 ON public.hr_employee_loan_transactions(accounting_voucher_id) WHERE accounting_voucher_id IS NOT NULL;

-- Dedicated receivable account for employee advances/loans. The bank account
-- remains configurable (default 1010) so the ledger follows the actual funding account.
INSERT INTO public.accounting_accounts(code,name,account_type,sub_type,is_system,description)
VALUES('1150','Employee loans receivable','asset','receivable',true,
       'Outstanding employee loans and recoverable staff advances')
ON CONFLICT(code) DO NOTHING;

DO $grants$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='superbajaar_user') THEN
  GRANT SELECT,INSERT,UPDATE ON public.hr_employee_loans,public.hr_employee_loan_transactions TO superbajaar_user;
 END IF;
END
$grants$;
