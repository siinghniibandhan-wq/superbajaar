-- Extend reviewed variable payroll earnings for final-settlement and arrears components.
-- Amounts are manager-entered and reasoned; no gratuity, leave-encashment or notice-pay
-- legal formula is assumed by the application.

ALTER TABLE public.hr_payroll_earning_adjustments
    DROP CONSTRAINT IF EXISTS hr_payroll_earning_adjustments_earning_type_check;

ALTER TABLE public.hr_payroll_earning_adjustments
    ADD CONSTRAINT hr_payroll_earning_adjustments_earning_type_check
    CHECK (earning_type IN (
        'overtime','incentive','bonus','arrears',
        'leave_encashment','gratuity','notice_pay','final_settlement'
    ));
