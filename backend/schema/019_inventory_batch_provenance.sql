-- Inventory batch manufacture-date and transfer provenance (migration 019).
-- Additive only; preserve the applied 000, 009, 017 and 018 migrations.

ALTER TABLE public.inventory_cost_layers
    ADD COLUMN IF NOT EXISTS manufacture_date date;

-- Backfill manufacture dates on original receipt layers first.
UPDATE public.inventory_cost_layers layer
   SET manufacture_date = line.manufacture_date
  FROM public.goods_receipt_lines line
 WHERE layer.goods_receipt_line_id = line.id
   AND layer.manufacture_date IS DISTINCT FROM line.manufacture_date;

-- Restore source GRN provenance for transfer layers created before this migration.
-- Recursive propagation handles stock transferred through multiple warehouses.
WITH RECURSIVE provenance AS (
    SELECT id, goods_receipt_line_id, manufacture_date
      FROM public.inventory_cost_layers
     WHERE source_layer_id IS NULL
       AND goods_receipt_line_id IS NOT NULL
    UNION ALL
    SELECT child.id, parent.goods_receipt_line_id, parent.manufacture_date
      FROM public.inventory_cost_layers child
      JOIN provenance parent ON child.source_layer_id = parent.id
)
UPDATE public.inventory_cost_layers target
   SET goods_receipt_line_id = COALESCE(target.goods_receipt_line_id, source.goods_receipt_line_id),
       manufacture_date = COALESCE(target.manufacture_date, source.manufacture_date)
  FROM provenance source
 WHERE target.id = source.id
   AND (target.goods_receipt_line_id IS NULL OR target.manufacture_date IS NULL);

-- Keep all provenance fields immutable after the layer is created.
CREATE OR REPLACE FUNCTION public.inventory_protect_cost_layer()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Inventory cost layers cannot be deleted; use a stock issue or reversal';
    END IF;
    IF NEW.variant_id IS DISTINCT FROM OLD.variant_id
       OR NEW.location_id IS DISTINCT FROM OLD.location_id
       OR NEW.receipt_movement_id IS DISTINCT FROM OLD.receipt_movement_id
       OR NEW.purchase_order_line_id IS DISTINCT FROM OLD.purchase_order_line_id
       OR NEW.goods_receipt_line_id IS DISTINCT FROM OLD.goods_receipt_line_id
       OR NEW.source_layer_id IS DISTINCT FROM OLD.source_layer_id
       OR NEW.batch_code IS DISTINCT FROM OLD.batch_code
       OR NEW.manufacture_date IS DISTINCT FROM OLD.manufacture_date
       OR NEW.expiry_date IS DISTINCT FROM OLD.expiry_date
       OR NEW.received_quantity IS DISTINCT FROM OLD.received_quantity
       OR NEW.unit_cost IS DISTINCT FROM OLD.unit_cost
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'Inventory cost layer source, batch and valuation fields are immutable';
    END IF;
    IF NEW.remaining_quantity > OLD.remaining_quantity THEN
        RAISE EXCEPTION 'Inventory cost layer quantity cannot be increased; create a new receipt layer';
    END IF;
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'inventory_protect_cost_layer_trg'
          AND tgrelid = 'public.inventory_cost_layers'::regclass
    ) THEN
        CREATE TRIGGER inventory_protect_cost_layer_trg
        BEFORE UPDATE OR DELETE ON public.inventory_cost_layers
        FOR EACH ROW EXECUTE FUNCTION public.inventory_protect_cost_layer();
    END IF;
END
$$;
