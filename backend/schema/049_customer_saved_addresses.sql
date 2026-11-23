-- Customer-owned delivery addresses. Existing browser-only addresses remain untouched.
CREATE TABLE IF NOT EXISTS customer_addresses (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer_accounts(id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (label IN ('Home','Work','Other')),
    recipient_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    landmark TEXT,
    pin_code CHAR(6) NOT NULL CHECK (pin_code ~ '^[1-9][0-9]{5}$'),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_customer_addresses_owner
    ON customer_addresses(customer_id, is_default DESC, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_addresses_single_default
    ON customer_addresses(customer_id) WHERE is_default = TRUE;
