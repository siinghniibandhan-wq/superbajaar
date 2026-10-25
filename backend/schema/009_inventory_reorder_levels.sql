-- Store a minimum stock threshold for each product variant in each warehouse.
-- This is configuration only; it does not add or change stock quantities.

CREATE TABLE IF NOT EXISTS public.sb_inventory_reorder_levels (
    id BIGSERIAL PRIMARY KEY,
    warehouse_id BIGINT NOT NULL,
    variant_id BIGINT NOT NULL,
    minimum_quantity INTEGER NOT NULL DEFAULT 0 CHECK (minimum_quantity >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sb_inventory_reorder_levels_warehouse_variant_key
        UNIQUE (warehouse_id, variant_id)
);

CREATE INDEX IF NOT EXISTS sb_inventory_reorder_levels_variant_idx
    ON public.sb_inventory_reorder_levels (variant_id);

CREATE INDEX IF NOT EXISTS sb_inventory_reorder_levels_warehouse_idx
    ON public.sb_inventory_reorder_levels (warehouse_id);
