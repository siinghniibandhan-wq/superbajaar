-- Automated purchase replenishment (migration 048).
-- Adds reorder logic to variants and tracks stock levels for automation.

-- 1. Add reorder configuration columns to variants
ALTER TABLE public.product_variants
    ADD COLUMN IF NOT EXISTS reorder_point numeric(12,2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS reorder_qty numeric(12,2) DEFAULT NULL;

-- 2. Add column to track when stock fell below reorder point
ALTER TABLE public.inventory
    ADD COLUMN IF NOT EXISTS min_stock_date timestamp with time zone DEFAULT NULL;

-- 3. Create index for efficient replenishment queries
CREATE INDEX IF NOT EXISTS idx_inventory_reorder_tracking
    ON public.inventory(product_id)
    WHERE quantity <= COALESCE((SELECT reorder_point FROM public.product_variants WHERE id = public.inventory.product_id), 0);

-- 4. Add constraint to ensure reorder_qty is not zero or negative when set
ALTER TABLE public.product_variants
    ADD CONSTRAINT IF NOT EXISTS variants_reorder_qty_positive_check
    CHECK (
        reorder_qty IS NULL
        OR (
            reorder_qty IS NOT NULL
            AND reorder_qty > 0
        )
    );

-- 5. Backfill existing variant data (no reorder points initially)
UPDATE public.product_variants
    SET
        reorder_point = NULL,
        reorder_qty = NULL
WHERE reorder_point IS NULL AND reorder_qty IS NULL;

-- 6. Backfill existing inventory data
UPDATE public.inventory
    SET min_stock_date = NULL
WHERE min_stock_date IS NULL;

-- 7. Create function to trigger automatic stock alert
CREATE OR REPLACE FUNCTION public.variant_stock_alerts()
RETURNS SETOF RECORD AS $$
DECLARE
    v RECORD;
    inv RECORD;
BEGIN
    -- Find variants with stock below reorder point
    FOR v IN
        SELECT p.id, p.name, p.sku, v.reorder_point, v.reorder_qty, v.id as variant_id
        FROM public.products p
        INNER JOIN public.product_variants v ON p.id = v.product_id
        WHERE p.status = 'active'
          AND v.reorder_point IS NOT NULL
          AND v.reorder_qty IS NOT NULL
          AND v.reorder_qty > 0
    LOOP
        -- Get current stock level
        SELECT INTO inv quantity, min_stock_date
        FROM public.inventory
        WHERE product_id = v.id;

        -- If stock is at or below reorder point
        IF inv IS NOT NULL AND inv.quantity <= v.reorder_point THEN
            -- If min_stock_date is NULL, this is the first time stock is low
            IF inv.min_stock_date IS NULL THEN
                UPDATE public.inventory
                SET min_stock_date = now()
                WHERE product_id = v.id;

                -- Return alert for monitoring
                RETURN NEXT ROW(v.id, v.name, v.sku, v.reorder_point, v.reorder_qty, inv.quantity);
            END IF;
        ELSE
            -- Stock is healthy, clear the alert
            UPDATE public.inventory
            SET min_stock_date = NULL
            WHERE product_id = v.id AND min_stock_date IS NOT NULL;
        END IF;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql;

-- 8. Add view for replenishment dashboard
CREATE OR REPLACE VIEW public.replenishment_view AS
SELECT
    p.id as product_id,
    p.name as product_name,
    p.slug as product_slug,
    v.id as variant_id,
    v.sku,
    v.name as variant_name,
    v.selling_price,
    v.reorder_point,
    v.reorder_qty,
    inv.quantity as current_stock,
    inv.min_stock_date,
    inv.updated_at,
    CASE
        WHEN inv.quantity <= v.reorder_point THEN 'out_of_stock'
        WHEN inv.quantity <= v.reorder_point * 1.5 THEN 'reorder_needed'
        ELSE 'in_stock'
    END as stock_status
FROM public.products p
INNER JOIN public.product_variants v ON p.id = v.product_id
LEFT JOIN public.inventory inv ON p.id = inv.product_id
WHERE p.status = 'active'
  AND v.reorder_point IS NOT NULL
  AND v.reorder_qty IS NOT NULL
  AND v.reorder_qty > 0;

-- 9. Grant permissions
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        GRANT SELECT, INSERT, UPDATE ON TABLE public.product_variants TO superbajaar_user;
        GRANT SELECT ON TABLE public.inventory TO superbajaar_user;
        GRANT SELECT, USAGE, EXECUTE ON FUNCTION public.variant_stock_alerts() TO superbajaar_user;
        GRANT SELECT ON VIEW public.replenishment_view TO superbajaar_user;
    END IF;
END
$grant$;
