-- HR enterprise workflow uniqueness constraints.
-- JSONB keeps workflow payloads flexible; these partial indexes enforce business identifiers.

CREATE UNIQUE INDEX IF NOT EXISTS hr_enterprise_candidate_email_uq
  ON public.hr_enterprise_records (lower((payload->>'email')))
  WHERE domain='recruitment' AND (payload->>'record_type')='candidate';

CREATE UNIQUE INDEX IF NOT EXISTS hr_enterprise_asset_tag_uq
  ON public.hr_enterprise_records (lower((payload->>'asset_tag')))
  WHERE domain='assets' AND (payload->>'record_type')='asset';

CREATE UNIQUE INDEX IF NOT EXISTS hr_enterprise_application_candidate_job_uq
  ON public.hr_enterprise_records ((payload->>'candidate_id'), (payload->>'job_id'))
  WHERE domain='recruitment' AND (payload->>'record_type')='application';

CREATE UNIQUE INDEX IF NOT EXISTS hr_enterprise_document_object_key_uq
  ON public.hr_enterprise_records ((payload->>'object_key'))
  WHERE domain='documents' AND (payload->>'record_type')='employee_document';

CREATE INDEX IF NOT EXISTS hr_enterprise_expiry_due_idx
  ON public.hr_enterprise_records(domain,due_date)
  WHERE domain IN ('documents','learning','assets','travel','exit','recruitment') AND due_date IS NOT NULL;
