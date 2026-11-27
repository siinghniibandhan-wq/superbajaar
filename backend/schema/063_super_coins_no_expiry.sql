-- Super Coins no longer expire. Every earned lot still needs an expires_at value,
-- so "no expiry" is stored as 100 years (see COIN_VALIDITY_DAYS in the app).
-- Extends only lots that have not expired yet. Lots already expired stay expired.
-- Idempotent: running it again changes nothing.
UPDATE public.loyalty_transactions
   SET expires_at = created_at + interval '36500 days'
 WHERE transaction_type = 'earn'
   AND expires_at > now()
   AND expires_at < created_at + interval '36500 days';
