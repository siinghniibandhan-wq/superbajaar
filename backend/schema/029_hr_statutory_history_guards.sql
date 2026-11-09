-- 029_hr_statutory_history_guards.sql
-- Additive, repeatable history protection. No rows, columns, grants or owners change.
--
-- Audit events are append-only, except the existing FK-driven actor_user_id
-- SET NULL behaviour when an application user is deleted.
-- Payroll snapshots cannot be edited. They may be deleted only while their
-- payroll run is draft/calculated, preserving the existing recalculation flow.

CREATE OR REPLACE FUNCTION public.guard_hr_statutory_audit_events()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'HR statutory audit events cannot be deleted';
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.establishment_id IS DISTINCT FROM OLD.establishment_id
       OR NEW.employee_id IS DISTINCT FROM OLD.employee_id
       OR NEW.policy_version_id IS DISTINCT FROM OLD.policy_version_id
       OR NEW.payroll_run_id IS DISTINCT FROM OLD.payroll_run_id
       OR NEW.event_type IS DISTINCT FROM OLD.event_type
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.before_state IS DISTINCT FROM OLD.before_state
       OR NEW.after_state IS DISTINCT FROM OLD.after_state
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'HR statutory audit events are append-only';
    END IF;

    IF NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       AND NEW.actor_user_id IS NOT NULL THEN
        RAISE EXCEPTION 'HR statutory audit event actor cannot be changed';
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.guard_hr_payroll_statutory_snapshots()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Payroll statutory snapshots cannot be edited; recalculate the draft run instead';
    END IF;

    -- Lock the parent run while checking status. This serializes snapshot
    -- deletion with payroll approval and prevents a concurrent approval race.
    SELECT status
      INTO v_status
      FROM public.hr_payroll_runs
     WHERE id = OLD.payroll_run_id
       FOR UPDATE;

    IF v_status IS NULL OR v_status NOT IN ('draft', 'calculated') THEN
        RAISE EXCEPTION 'Payroll statutory snapshots of approved, paid or void runs cannot be deleted';
    END IF;

    RETURN OLD;
END;
$function$;

DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_trigger
         WHERE tgrelid = 'public.hr_statutory_audit_events'::regclass
           AND tgname = 'trg_guard_hr_statutory_audit_events'
           AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_guard_hr_statutory_audit_events
            BEFORE UPDATE OR DELETE ON public.hr_statutory_audit_events
            FOR EACH ROW
            EXECUTE FUNCTION public.guard_hr_statutory_audit_events();
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_trigger
         WHERE tgrelid = 'public.hr_payroll_statutory_snapshots'::regclass
           AND tgname = 'trg_guard_hr_payroll_statutory_snapshots'
           AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_guard_hr_payroll_statutory_snapshots
            BEFORE UPDATE OR DELETE ON public.hr_payroll_statutory_snapshots
            FOR EACH ROW
            EXECUTE FUNCTION public.guard_hr_payroll_statutory_snapshots();
    END IF;
END
$guard$;
