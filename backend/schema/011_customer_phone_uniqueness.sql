-- Enforce one customer account per canonicalised mobile number.
-- Idempotent. Existing data is not modified or deleted.
CREATE UNIQUE INDEX IF NOT EXISTS customer_accounts_phone_digits_uidx
    ON customer_accounts (
      (CASE
        WHEN length(regexp_replace(phone, '[^0-9]', '', 'g')) = 12
          AND left(regexp_replace(phone, '[^0-9]', '', 'g'), 2) = '91'
          THEN right(regexp_replace(phone, '[^0-9]', '', 'g'), 10)
        WHEN length(regexp_replace(phone, '[^0-9]', '', 'g')) = 11
          AND left(regexp_replace(phone, '[^0-9]', '', 'g'), 1) = '0'
          THEN right(regexp_replace(phone, '[^0-9]', '', 'g'), 10)
        ELSE regexp_replace(phone, '[^0-9]', '', 'g')
      END)
    )
    WHERE phone IS NOT NULL
      AND regexp_replace(phone, '[^0-9]', '', 'g') <> '';
