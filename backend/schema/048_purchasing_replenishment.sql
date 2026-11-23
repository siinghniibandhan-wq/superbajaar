-- Automated purchase replenishment (migration 048), corrected.
-- Adds reorder settings to variants and a low-stock date to inventory.

-- 1. Reorder configuration columns on variants
ALTER TABLE public.product_variants
    ADD COLUMN IF NOT EXISTS reorder_point numeric(12,2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS reorder_qty numeric(12,2) DEFAULT NULL;

-- 2. Column that tracks when stock first fell to the reorder point
ALTER TABLE public.inventory
    ADD COLUMN IF NOT EXISTS min_stock_date timestamp with time zone DEFAULT NULL;

-- 3. Plain index for replenishment queries (a partial index cannot contain a subquery)
CREATE INDEX IF NOT EXISTS idx_inventory_reorder_tracking
    ON public.inventory (quantity, product_id);

-- 4. reorder_qty must be empty or above zero
DO $constraint$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'variants_reorder_qty_positive_check'
          AND conrelid = 'public.product_variants'::regclass
    ) THEN
        ALTER TABLE public.product_variants
            ADD CONSTRAINT variants_reorder_qty_positive_check
            CHECK (reorder_qty IS NULL OR reorder_qty > 0);
    END IF;
END
$constraint$;

-- 5. Stock alert function
CREATE OR REPLACE FUNCTION public.variant_stock_alerts()
RETURNS TABLE (
    alert_product_id bigint,
    alert_product_name text,
    alert_sku text,
    alert_reorder_point numeric,
    alert_reorder_qty numeric,
    alert_stock integer
) AS $$
DECLARE
    rec RECORD;
    cur_qty integer;
    cur_min_date timestamp with time zone;
    inv_found boolean;
BEGIN
    FOR rec IN
        SELECT p.id AS pid, p.name AS pname, pv.sku AS psku,
               pv.reorder_point AS rp, pv.reorder_qty AS rq
        FROM public.products p
        INNER JOIN public.product_variants pv ON p.id = pv.product_id
        WHERE p.status = 'active'
          AND pv.reorder_point IS NOT NULL
          AND pv.reorder_qty IS NOT NULL
          AND pv.reorder_qty > 0
    LOOP
        SELECT i.quantity, i.min_stock_date
          INTO cur_qty, cur_min_date
        FROM public.inventory i
        WHERE i.product_id = rec.pid;
        inv_found := FOUND;

        IF inv_found AND cur_qty <= rec.rp THEN
            IF cur_min_date IS NULL THEN
                UPDATE public.inventory
                   SET min_stock_date = now()
                 WHERE product_id = rec.pid;

                alert_product_id := rec.pid;
                alert_product_name := rec.pname;
                alert_sku := rec.psku;
                alert_reorder_point := rec.rp;
                alert_reorder_qty := rec.rq;
                alert_stock := cur_qty;
                RETURN NEXT;
            END IF;
        ELSE
            UPDATE public.inventory
               SET min_stock_date = NULL
             WHERE product_id = rec.pid AND min_stock_date IS NOT NULL;
        END IF;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql;

-- 6. View for the replenishment dashboard
CREATE OR REPLACE VIEW public.replenishment_view AS
SELECT
    p.id AS product_id,
    p.name AS product_name,
    p.slug AS product_slug,
    v.id AS variant_id,
    v.sku,
    v.sku AS variant_name,
    v.selling_price,
    v.reorder_point,
    v.reorder_qty,
    inv.quantity AS current_stock,
    inv.min_stock_date,
    inv.updated_at,
    CASE
        WHEN inv.quantity <= v.reorder_point THEN 'out_of_stock'
        WHEN inv.quantity <= v.reorder_point * 1.5 THEN 'reorder_needed'
        ELSE 'in_stock'
    END AS stock_status
FROM public.products p
INNER JOIN public.product_variants v ON p.id = v.product_id
LEFT JOIN public.inventory inv ON p.id = inv.product_id
WHERE p.status = 'active'
  AND v.reorder_point IS NOT NULL
  AND v.reorder_qty IS NOT NULL
  AND v.reorder_qty > 0;

-- 7. Permissions (only if the role exists)
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superbajaar_user') THEN
        GRANT SELECT, INSERT, UPDATE ON TABLE public.product_variants TO superbajaar_user;
        GRANT SELECT ON TABLE public.inventory TO superbajaar_user;
        GRANT EXECUTE ON FUNCTION public.variant_stock_alerts() TO superbajaar_user;
        GRANT SELECT ON TABLE public.replenishment_view TO superbajaar_user;
    END IF;
END
$grant$;
