-- Recruitment indexes must match the workflow's definition of an active record.
-- Rejected/withdrawn applications and archived candidates may be re-entered.
DROP INDEX IF EXISTS public.hr_enterprise_candidate_email_uq;
CREATE UNIQUE INDEX hr_enterprise_candidate_email_uq
  ON public.hr_enterprise_records (lower((payload->>'email')))
  WHERE domain='recruitment'
    AND (payload->>'record_type')='candidate'
    AND status NOT IN ('archived','withdrawn');

DROP INDEX IF EXISTS public.hr_enterprise_application_candidate_job_uq;
CREATE UNIQUE INDEX hr_enterprise_application_candidate_job_uq
  ON public.hr_enterprise_records ((payload->>'candidate_id'),(payload->>'job_id'))
  WHERE domain='recruitment'
    AND (payload->>'record_type')='application'
    AND status NOT IN ('rejected','withdrawn','archived');

CREATE UNIQUE INDEX IF NOT EXISTS hr_enterprise_active_offer_application_uq
  ON public.hr_enterprise_records ((payload->>'application_id'))
  WHERE domain='recruitment'
    AND (payload->>'record_type')='offer'
    AND status NOT IN ('rejected','withdrawn','archived','expired','hired');
