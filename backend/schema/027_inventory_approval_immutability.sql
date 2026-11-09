-- Protect maker-checker request evidence and constrain lifecycle transitions.
CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_event_approval_open_payload
    ON public.inventory_event_approval_requests(establishment_id,policy_version_id,event_type,payload_hash)
    WHERE status IN ('pending','approved');

CREATE OR REPLACE FUNCTION public.guard_inventory_event_approval_request()
RETURNS trigger
LANGUAGE plpgsql
AS $inventory_approval_guard$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Inventory approval requests cannot be deleted';
    END IF;
    IF NEW.establishment_id IS DISTINCT FROM OLD.establishment_id
       OR NEW.policy_version_id IS DISTINCT FROM OLD.policy_version_id
       OR NEW.event_type IS DISTINCT FROM OLD.event_type
       OR NEW.location_id IS DISTINCT FROM OLD.location_id
       OR NEW.payload IS DISTINCT FROM OLD.payload
       OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash
       OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
       OR NEW.created_by_email IS DISTINCT FROM OLD.created_by_email
       OR NEW.created_by_role IS DISTINCT FROM OLD.created_by_role
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Inventory approval request evidence is immutable';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT ((OLD.status='pending' AND NEW.status IN ('approved','rejected'))
             OR (OLD.status='approved' AND NEW.status='posted')) THEN
            RAISE EXCEPTION 'Invalid inventory approval request status transition';
        END IF;
    ELSIF NEW.posted_at IS DISTINCT FROM OLD.posted_at THEN
        RAISE EXCEPTION 'Inventory approval posted timestamp is immutable';
    END IF;
    RETURN NEW;
END;
$inventory_approval_guard$;

DROP TRIGGER IF EXISTS trg_inventory_event_approval_request_guard
    ON public.inventory_event_approval_requests;
CREATE TRIGGER trg_inventory_event_approval_request_guard
    BEFORE UPDATE OR DELETE ON public.inventory_event_approval_requests
    FOR EACH ROW EXECUTE FUNCTION public.guard_inventory_event_approval_request();
