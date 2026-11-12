-- 045: Permit explicit customer cancellation in the append-only identity audit trail.
-- Existing audit events and request history remain unchanged.

ALTER TABLE public.identity_events
    DROP CONSTRAINT IF EXISTS identity_events_event_type_check;

ALTER TABLE public.identity_events
    ADD CONSTRAINT identity_events_event_type_check
    CHECK (event_type IN (
        'party_created','party_updated','profile_linked','profile_unlinked',
        'auth_account_linked','auth_account_unlinked','contact_added','contact_verified',
        'contact_revoked','relationship_created','relationship_approved','relationship_revoked',
        'link_requested','link_approved','link_rejected','link_cancelled',
        'party_merged','party_split','party_deactivated','party_reactivated'
    ));
