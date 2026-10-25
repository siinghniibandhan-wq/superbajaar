-- Tables used by the admin dashboard operations module (warehouses, stock ledger, procurement,
-- receipts, invoices, returns, tax and document tracking).
-- Previously the API tried to create these at request time, but the API database role is not
-- allowed to create tables, so every admin screen failed. Additive only: new empty tables.
-- sb_vendors and sb_accounts already exist and are NOT recreated.

-- Catalogue attribute definitions are referenced by the admin attribute and variant APIs.
-- Keep this table in the numbered schema migration, not request-time DDL.
CREATE TABLE IF NOT EXISTS catalog_attributes(
      id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, values_json JSONB NOT NULL DEFAULT '[]',
      display_type TEXT NOT NULL DEFAULT 'text' CHECK (display_type IN ('text','color','image','dropdown','button')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS catalog_product_tax(
      product_id BIGINT PRIMARY KEY, hsn_code TEXT NOT NULL, updated_by BIGINT,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS product_attribute_assignments(
      product_id BIGINT NOT NULL, attribute_id BIGINT NOT NULL REFERENCES catalog_attributes(id) ON DELETE CASCADE,
      PRIMARY KEY(product_id,attribute_id));

CREATE TABLE IF NOT EXISTS variant_attribute_values(
      variant_id BIGINT NOT NULL, attribute_id BIGINT NOT NULL REFERENCES catalog_attributes(id),
      value TEXT NOT NULL, PRIMARY KEY(variant_id,attribute_id));

CREATE TABLE IF NOT EXISTS sb_warehouses(
      id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE, address TEXT NOT NULL DEFAULT '',
      pincode TEXT NOT NULL DEFAULT '', serviceable_pincodes JSONB NOT NULL DEFAULT '[]',
      locations JSONB NOT NULL DEFAULT '[]', active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_inventory_ledger(
      id BIGSERIAL PRIMARY KEY, warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id),
      variant_id BIGINT NOT NULL, quantity_delta INTEGER NOT NULL, movement_type TEXT NOT NULL,
      reference TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', actor_id BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_procurements(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, purchase_order_reference TEXT UNIQUE, vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
      status TEXT NOT NULL DEFAULT 'draft', items JSONB NOT NULL DEFAULT '[]', expected_date DATE,
      created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_vendor_dispatches(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, procurement_id BIGINT NOT NULL REFERENCES sb_procurements(id),
      vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id), items JSONB NOT NULL, carrier TEXT NOT NULL DEFAULT '',
      tracking_reference TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'dispatched',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_receipts(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, procurement_id BIGINT NOT NULL REFERENCES sb_procurements(id),
      warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id), status TEXT NOT NULL DEFAULT 'inspection',
      items JSONB NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '', received_by BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_invoices(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, source_channel TEXT NOT NULL,
      source_id BIGINT, customer_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'issued',
      subtotal NUMERIC(14,2) NOT NULL DEFAULT 0, discount_total NUMERIC(14,2) NOT NULL DEFAULT 0, tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      total NUMERIC(14,2) NOT NULL DEFAULT 0, paid_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      items JSONB NOT NULL DEFAULT '[]', created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_supplier_bills(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
      procurement_id BIGINT REFERENCES sb_procurements(id), vendor_invoice_number TEXT NOT NULL,
      amount NUMERIC(14,2) NOT NULL CHECK(amount>=0), tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      paid_total NUMERIC(14,2) NOT NULL DEFAULT 0, due_date DATE, status TEXT NOT NULL DEFAULT 'submitted',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(vendor_id,vendor_invoice_number));

CREATE TABLE IF NOT EXISTS sb_payments(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_id BIGINT NOT NULL REFERENCES sb_invoices(id),
      amount NUMERIC(14,2) NOT NULL CHECK(amount>0), method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'posted',
      recorded_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_returns(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_reference TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'requested', reason TEXT NOT NULL DEFAULT '', items JSONB NOT NULL DEFAULT '[]',
      origin_warehouse_id BIGINT, refund_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
      created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_credit_notes(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_reference TEXT NOT NULL,
      return_reference TEXT NOT NULL UNIQUE, amount NUMERIC(14,2) NOT NULL CHECK(amount>=0),
      status TEXT NOT NULL DEFAULT 'posted', created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_tax_config(
      id SMALLINT PRIMARY KEY CHECK(id=1), seller_gstin TEXT NOT NULL DEFAULT '',
      seller_state_code TEXT NOT NULL DEFAULT '', rates_json JSONB NOT NULL DEFAULT '{}',
      updated_by BIGINT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_journal_entries(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, source_reference TEXT NOT NULL,
      entry_date DATE NOT NULL DEFAULT CURRENT_DATE, memo TEXT NOT NULL DEFAULT '', lines JSONB NOT NULL,
      posted BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_document_events(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL, event_type TEXT NOT NULL,
      from_status TEXT, to_status TEXT, actor_id BIGINT, details JSONB NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS sb_document_registry(
      reference TEXT PRIMARY KEY, document_type TEXT NOT NULL, document_id BIGINT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now());

-- Older operations installs created sb_accounts with only an "active" flag.
-- Add the columns required by the current accounting and operations APIs without dropping data.
ALTER TABLE sb_accounts ADD COLUMN IF NOT EXISTS detail_type TEXT NOT NULL DEFAULT 'other';
ALTER TABLE sb_accounts ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sb_accounts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
DO $
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='sb_accounts' AND column_name='active'
  ) THEN
    UPDATE sb_accounts SET is_active = active WHERE is_active IS DISTINCT FROM active;
  END IF;
END $;

-- The operations module expects a vendor status; existing vendors become 'active'.
ALTER TABLE sb_vendors ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

CREATE UNIQUE INDEX IF NOT EXISTS sb_procurements_po_ref_uidx ON sb_procurements(purchase_order_reference) WHERE purchase_order_reference IS NOT NULL;
CREATE INDEX IF NOT EXISTS sb_events_ref_idx ON sb_document_events(reference,created_at);
CREATE INDEX IF NOT EXISTS sb_inventory_variant_idx ON sb_inventory_ledger(variant_id,warehouse_id,created_at);
