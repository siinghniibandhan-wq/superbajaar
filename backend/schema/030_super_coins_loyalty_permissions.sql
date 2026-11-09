-- 030: restore least-privilege application access to Super Coins ledger tables.
-- Migration 028 created these tables as postgres but did not grant the application role.
-- Additive and repeat-safe; grants only the operations used by loyalty_redemption.py.
-- The schema runner executes this file in its own transaction.

DO $loyalty_grants$
DECLARE
    v_table text;
    v_sequence text;
BEGIN
    -- Keep local/disposable schema tests usable when the application role is absent.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        EXECUTE 'GRANT SELECT, INSERT ON TABLE public.loyalty_expiration_allocations TO superbajaar_user';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.loyalty_order_redemptions TO superbajaar_user';
        EXECUTE 'GRANT INSERT ON TABLE public.loyalty_redemption_restorations TO superbajaar_user';

        -- Resolve the actual serial sequence attached to each id column rather
        -- than assuming PostgreSQL's generated sequence names.
        FOREACH v_table IN ARRAY ARRAY[
            'loyalty_expiration_allocations',
            'loyalty_order_redemptions',
            'loyalty_redemption_restorations'
        ]
        LOOP
            v_sequence := pg_get_serial_sequence(
                format('public.%I', v_table),
                'id'
            );

            IF v_sequence IS NULL THEN
                RAISE EXCEPTION
                    'Could not resolve id sequence for public.%; verify migration 028 before applying migration 030',
                    v_table;
            END IF;

            EXECUTE format(
                'GRANT USAGE, SELECT ON SEQUENCE %s TO %I',
                v_sequence::regclass,
                'superbajaar_user'
            );
        END LOOP;
    END IF;
END
$loyalty_grants$;
