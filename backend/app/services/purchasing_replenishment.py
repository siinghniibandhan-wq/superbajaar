"""Automated purchase replenishment service.

This service generates draft purchase orders based on inventory levels
compared to reorder points configured on variants.
"""

from datetime import datetime, date
from typing import List, Optional
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException

from app.core.config import settings


class VariantReorderData:
    """Variant data with inventory and reorder configuration."""

    def __init__(
        self,
        id: int,
        product_id: int,
        name: str,
        sku: str,
        reorder_point: Optional[float],
        reorder_qty: Optional[float],
        current_stock: Optional[float],
        min_stock_date: Optional[datetime],
    ):
        self.id = id
        self.product_id = product_id
        self.name = name
        self.sku = sku
        self.reorder_point = reorder_point
        self.reorder_qty = reorder_qty
        self.current_stock = current_stock
        self.min_stock_date = min_stock_date


class ReplenishmentResult:
    """Result of a replenishment operation."""

    def __init__(
        self,
        variant_id: int,
        product_name: str,
        sku: str,
        reorder_qty: float,
        new_draft_po_id: Optional[int] = None,
        reason: str = "stock_below_reorder_point",
    ):
        self.variant_id = variant_id
        self.product_name = product_name
        self.sku = sku
        self.reorder_qty = reorder_qty
        self.new_draft_po_id = new_draft_po_id
        self.reason = reason


def _connect() -> psycopg.Connection:
    """Connect to database with error handling."""
    if not settings.database_url:
        raise HTTPException(503, "Purchasing database is not configured")

    try:
        conn = psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
        conn.autocommit = False
        return conn
    except psycopg.Error as exc:
        raise HTTPException(503, "Purchasing database unavailable") from exc


def get_out_of_stock_variants(conn: psycopg.Connection) -> List[VariantReorderData]:
    """Get variants that need replenishment.

    Args:
        conn: Database connection

    Returns:
        List of variants with stock below reorder point
    """
    query = """
        SELECT
            v.id,
            v.product_id,
            p.name as product_name,
            v.sku,
            v.reorder_point,
            v.reorder_qty,
            inv.quantity as current_stock,
            inv.min_stock_date
        FROM public.product_variants v
        INNER JOIN public.products p ON v.product_id = p.id
        LEFT JOIN public.inventory inv ON p.id = inv.product_id
        WHERE p.status = 'active'
          AND v.reorder_point IS NOT NULL
          AND v.reorder_qty IS NOT NULL
          AND v.reorder_qty > 0
          AND (inv.quantity IS NULL OR inv.quantity <= v.reorder_point)
        ORDER BY
            inv.quantity NULLS LAST,
            v.reorder_point ASC,
            p.name ASC
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

        return [
            VariantReorderData(
                id=row["id"],
                product_id=row["product_id"],
                name=row["product_name"],
                sku=row["sku"],
                reorder_point=row["reorder_point"],
                reorder_qty=row["reorder_qty"],
                current_stock=row["current_stock"],
                min_stock_date=row["min_stock_date"],
            )
            for row in rows
        ]


def get_replenishment_report(conn: psycopg.Connection) -> List[VariantReorderData]:
    """Get a report of all variants with reorder configuration.

    Args:
        conn: Database connection

    Returns:
        List of all variants with reorder settings and current stock
    """
    query = """
        SELECT
            v.id,
            v.product_id,
            p.name as product_name,
            v.sku,
            v.reorder_point,
            v.reorder_qty,
            inv.quantity as current_stock,
            inv.min_stock_date
        FROM public.product_variants v
        INNER JOIN public.products p ON v.product_id = p.id
        LEFT JOIN public.inventory inv ON p.id = inv.product_id
        WHERE p.status = 'active'
          AND v.reorder_point IS NOT NULL
          AND v.reorder_qty IS NOT NULL
          AND v.reorder_qty > 0
        ORDER BY p.name ASC, v.sku ASC
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

        return [
            VariantReorderData(
                id=row["id"],
                product_id=row["product_id"],
                name=row["product_name"],
                sku=row["sku"],
                reorder_point=row["reorder_point"],
                reorder_qty=row["reorder_qty"],
                current_stock=row["current_stock"],
                min_stock_date=row["min_stock_date"],
            )
            for row in rows
        ]


def generate_draft_purchase_orders(
    conn: psycopg.Connection,
    limit: int = 1000,
) -> List[ReplenishmentResult]:
    """Generate draft purchase orders for variants that need replenishment.

    Args:
        conn: Database connection
        limit: Maximum number of PO lines to include

    Returns:
        List of replenishment results with details about generated POs

    Raises:
        HTTPException: If database operation fails
    """
    try:
        # Get all variants that need replenishment
        variants = get_out_of_stock_variants(conn)

        if not variants:
            return []

        results = []

        with conn.cursor() as cur:
            # Check if a draft PO exists for today
            today = datetime.now().date()
            cur.execute(
                """
                SELECT id, requisition_number
                FROM public.purchase_requisitions
                WHERE status = 'draft'
                  AND DATE(created_at) = %s
                LIMIT 1
            """,
                (today,),
            )
            existing_po = cur.fetchone()

            if existing_po:
                requisition_id = existing_po["id"]
                requisition_number = existing_po["requisition_number"]
            else:
                # Create a new draft requisition
                requisition_number = f"RPL-{today.strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}"
                cur.execute(
                    """
                    INSERT INTO public.purchase_requisitions (
                        requisition_number, requester_user_id, requester_email, department,
                        cost_centre, location_id, justification, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft')
                    RETURNING id
                """,
                    (
                        requisition_number,
                        1,  # Assuming system user for automation
                        "replenishment-bot@superbaaar.local",
                        "replenishment",
                        "automated",
                        None,  # location_id
                        "Automated replenishment generated by system based on reorder points",
                    ),
                )
                requisition_id = cur.fetchone()["id"]

            # Add lines to the requisition
            for variant in variants[:limit]:
                # Calculate quantity to order
                qty_to_order = variant.reorder_qty

                # Check if this variant already has a line in the PO
                cur.execute(
                    """
                    SELECT id FROM public.purchase_requisition_lines
                    WHERE requisition_id = %s AND variant_id = %s
                    LIMIT 1
                """,
                    (requisition_id, variant.id),
                )
                existing_line = cur.fetchone()

                if not existing_line:
                    cur.execute(
                        """
                        INSERT INTO public.purchase_requisition_lines (
                            requisition_id, variant_id, quantity, estimated_unit_cost
                        )
                        VALUES (%s, %s, %s, NULL)
                        RETURNING id
                    """,
                        (requisition_id, variant.id, qty_to_order),
                    )

                results.append(
                    ReplenishmentResult(
                        variant_id=variant.id,
                        product_name=variant.name,
                        sku=variant.sku,
                        reorder_qty=variant.reorder_qty,
                        reason="stock_below_reorder_point",
                    )
                )

        conn.commit()
        return results

    except psycopg.Error as exc:
        conn.rollback()
        raise HTTPException(503, "Failed to generate replenishment POs") from exc


def update_variant_reorder_settings(
    variant_id: int,
    reorder_point: Optional[float] = None,
    reorder_qty: Optional[float] = None,
) -> bool:
    """Update reorder point and quantity for a variant.

    Args:
        variant_id: Variant ID
        reorder_point: Minimum stock threshold
        reorder_qty: Quantity to order when stock is low

    Returns:
        True if update was successful

    Raises:
        HTTPException: If variant not found or update fails
    """
    conn = _connect()
    try:
        query = """
            UPDATE public.product_variants
            SET
                reorder_point = COALESCE(%s, reorder_point),
                reorder_qty = COALESCE(%s, reorder_qty)
            WHERE id = %s
        """
        with conn.cursor() as cur:
            cur.execute(query, (reorder_point, reorder_qty, variant_id))
            result = conn.commit()
        return True
    except psycopg.Error as exc:
        conn.rollback()
        raise HTTPException(503, "Failed to update reorder settings") from exc
    finally:
        conn.close()


def clear_reorder_alerts(product_id: int) -> bool:
    """Clear reorder alert for a product when stock is replenished.

    Args:
        product_id: Product ID

    Returns:
        True if cleared successfully
    """
    conn = _connect()
    try:
        query = """
            UPDATE public.inventory
            SET min_stock_date = NULL
            WHERE product_id = %s AND min_stock_date IS NOT NULL
        """
        with conn.cursor() as cur:
            cur.execute(query, (product_id,))
            conn.commit()
        return True
    except psycopg.Error as exc:
        conn.rollback()
        raise HTTPException(503, "Failed to clear reorder alerts") from exc
    finally:
        conn.close()


def get_replenishment_stats(conn: psycopg.Connection) -> dict:
    """Get statistics about replenishment needs.

    Args:
        conn: Database connection

    Returns:
        Dictionary with replenishment statistics
    """
    query = """
        SELECT
            COUNT(*) as total_configured_variants,
            COUNT(*) FILTER (WHERE quantity IS NOT NULL AND quantity <= reorder_point) as stock_below_reorder,
            COUNT(*) FILTER (WHERE quantity IS NULL) as out_of_stock,
            AVG(reorder_point) as avg_reorder_point,
            AVG(reorder_qty) as avg_reorder_qty
        FROM public.product_variants v
        INNER JOIN public.products p ON v.product_id = p.id
        LEFT JOIN public.inventory inv ON p.id = inv.product_id
        WHERE p.status = 'active'
          AND v.reorder_point IS NOT NULL
          AND v.reorder_qty IS NOT NULL
          AND v.reorder_qty > 0
    """

    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()

        return {
            "total_configured_variants": row["total_configured_variants"],
            "stock_below_reorder": row["stock_below_reorder"],
            "out_of_stock": row["out_of_stock"],
            "avg_reorder_point": float(row["avg_reorder_point"]) if row["avg_reorder_point"] else 0.0,
            "avg_reorder_qty": float(row["avg_reorder_qty"]) if row["avg_reorder_qty"] else 0.0,
        }
