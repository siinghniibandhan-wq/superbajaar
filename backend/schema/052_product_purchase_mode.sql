-- How a product is bought.
-- packed (default): each variant is bought as it is, e.g. atta 5 kg. Existing behaviour.
-- bulk: bought once in bulk (kg, litre or piece) and then split into variants.
-- A product with no row here is treated as packed, so nothing changes until a product is marked bulk.
CREATE TABLE IF NOT EXISTS product_purchase_modes (
    product_id BIGINT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    purchase_mode TEXT NOT NULL DEFAULT 'packed' CHECK (purchase_mode IN ('packed','bulk')),
    bulk_unit TEXT CHECK (bulk_unit IN ('kg','litre','piece')),
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT product_purchase_modes_bulk_needs_unit CHECK (purchase_mode = 'packed' OR bulk_unit IS NOT NULL)
);
