-- 073: employee job grades used by role/grade based travel policy controls.
ALTER TABLE public.hr_employees
    ADD COLUMN IF NOT EXISTS job_grade text NOT NULL DEFAULT 'ungraded';
ALTER TABLE public.hr_employees
    ADD CONSTRAINT hr_employees_job_grade_nonblank
    CHECK (length(trim(job_grade)) > 0);
CREATE INDEX IF NOT EXISTS hr_employees_job_grade_status_idx
    ON public.hr_employees(job_grade,status);
