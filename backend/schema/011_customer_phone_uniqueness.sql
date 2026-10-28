-- Enforce one customer account per normalized mobile number.
-- Idempotent. Existing data is not modified or deleted; duplicate historical
-- phone values, if any, must be reviewed before this unique index can be applied.
CREATE UNIQUE INDEX IF NOT EXISTS customer_accounts_phone_digits_uidx
    ON customer_accounts (regexp_replace(phone, '[^0-9]', '', 'g'))
    WHERE phone IS NOT NULL
      AND regexp_replace(phone, '[^0-9]', '', 'g') <> '';
