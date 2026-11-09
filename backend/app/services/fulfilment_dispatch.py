"""Application service for the Inventory-to-Fulfilment dispatch boundary.

The caller owns the PostgreSQL transaction and shipment/order row locks.
This service coordinates stock issue and final COGS posting within that
transaction; it does not create a second stock ledger.
"""
from decimal import Decimal
import hashlib
import json

from app.services.order_inventory import (
    dispatch_order_stock,
    order_fulfilment_started,
    order_has_reservation,
)


class FulfilmentDispatchError(ValueError):
    """Expected dispatch conflict with an HTTP-compatible status code."""

    def __init__(self, detail: str, status_code: int = 409):
        super().__init__(detail)
        self.status_code = status_code


def dispatch_payload_hash(lines, package_lines=None):
    """Fingerprint dispatch quantity intent independently of line ordering."""
    if lines is None:
        payload = {"mode": "all_outstanding"}
    else:
        normalized = []
        for line in lines:
            if isinstance(line, dict):
                variant_id, quantity = line["variant_id"], line["quantity"]
            else:
                variant_id, quantity = line.variant_id, line.quantity
            normalized.append({"variant_id": int(variant_id), "quantity": str(Decimal(str(quantity)).normalize())})
        payload = {"mode": "selected_quantities", "lines": sorted(normalized, key=lambda item: item["variant_id"])}
    if package_lines is not None:
        package_payload = []
        for line in package_lines:
            if isinstance(line, dict):
                package_line_id, quantity = line["package_line_id"], line["quantity"]
            else:
                package_line_id, quantity = line.package_line_id, line.quantity
            package_payload.append({"package_line_id": int(package_line_id), "quantity": str(Decimal(str(quantity)).normalize())})
        payload["package_lines"] = sorted(package_payload, key=lambda item: item["package_line_id"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dispatch_history_note(dispatch_id, payload_hash, note):
    marker = f"[dispatch-id:{dispatch_id};payload-sha256:{payload_hash}]"
    return marker + (" " + note if note else "")


def validate_dispatch_replay(existing_note, dispatch_id, payload_hash):
    """Return True for an exact replay; reject identity reuse with changed intent."""
    if not existing_note:
        return False
    marker_end = existing_note.find("]")
    if marker_end < 0:
        return False
    marker = existing_note[:marker_end + 1]
    prefix = f"[dispatch-id:{dispatch_id};payload-sha256:"
    if not marker.startswith(prefix):
        return False
    recorded_hash = marker[len(prefix):-1]
    if recorded_hash != payload_hash:
        raise FulfilmentDispatchError("Dispatch ID was already used with a different payload")
    return True


def dispatch_shipment(
    conn, *, shipment_id: int, order_id: int, order_status: str,
    order_number: str, customer_name: str, dispatch_id: str,
    dispatch_lines, package_lines=None, note: str | None,
    actor_id: int | None, actor_email: str | None,
):
    """Issue reserved stock and record immutable dispatch evidence atomically."""
    if not actor_email:
        raise FulfilmentDispatchError("A valid staff session is required", status_code=401)

    payload_hash = dispatch_payload_hash(dispatch_lines, package_lines)
    previous_event = conn.execute(
        "SELECT id,payload_hash FROM fulfilment_dispatch_events WHERE shipment_id=%s AND dispatch_id=%s FOR UPDATE",
        (shipment_id, dispatch_id),
    ).fetchone()
    if previous_event is not None:
        if previous_event["payload_hash"] != payload_hash:
            raise FulfilmentDispatchError("Dispatch ID was already used with a different payload")
        return {"duplicate": True, "history_note": None}

    has_reservation = order_has_reservation(conn, order_id)
    prior_dispatch_event = conn.execute(
        "SELECT e.id FROM fulfilment_dispatch_events e JOIN deliveries d ON d.id=e.shipment_id WHERE d.order_id=%s LIMIT 1",
        (order_id,),
    ).fetchone()
    package_allocations = []
    requested_from_packages = None
    if package_lines is not None:
        if dispatch_lines is not None:
            raise FulfilmentDispatchError("Specify package lines or variant quantities, not both", status_code=422)
        requested_from_packages = {}
        for item in package_lines:
            package_line_id = int(item["package_line_id"] if isinstance(item, dict) else item.package_line_id)
            quantity = Decimal(str(item["quantity"] if isinstance(item, dict) else item.quantity))
            package_line = conn.execute(
                "SELECT pl.id,pl.order_line_id,pl.variant_id,pl.quantity,p.status,p.shipment_id,"
                "COALESCE((SELECT sum(el.quantity) FROM fulfilment_dispatch_event_lines el WHERE el.package_line_id=pl.id),0) AS dispatched_quantity "
                "FROM fulfilment_package_lines pl JOIN fulfilment_packages p ON p.id=pl.package_id "
                "WHERE pl.id=%s AND p.shipment_id=%s FOR UPDATE OF pl,p",
                (package_line_id, shipment_id),
            ).fetchone()
            if package_line is None or package_line["status"] != "sealed":
                raise FulfilmentDispatchError("Every dispatched package line must belong to this shipment and be sealed", 409)
            available = Decimal(str(package_line["quantity"])) - Decimal(str(package_line["dispatched_quantity"]))
            if quantity <= 0 or quantity > available:
                raise FulfilmentDispatchError("Package dispatch quantity exceeds the sealed, not-yet-dispatched quantity", 409)
            package_allocations.append({"package_line_id": package_line_id, "order_line_id": int(package_line["order_line_id"]),
                                        "variant_id": int(package_line["variant_id"]), "quantity": quantity})
            variant_id = int(package_line["variant_id"])
            requested_from_packages[variant_id] = requested_from_packages.get(variant_id, Decimal("0")) + quantity

    legacy_preissued = order_status == "dispatched" and not has_reservation and order_fulfilment_started(conn, order_id) and prior_dispatch_event is None
    if order_status == "dispatched" and not has_reservation and not legacy_preissued:
        raise FulfilmentDispatchError("No outstanding reserved quantity remains for another dispatch event")
    max_issue_id = conn.execute("SELECT COALESCE(max(id),0) AS max_id FROM inventory_order_issues WHERE order_id=%s", (order_id,)).fetchone()["max_id"]
    if legacy_preissued:
        prior_handover = conn.execute(
            "SELECT id FROM fulfilment_dispatch_events WHERE shipment_id<>%s AND shipment_id IN (SELECT id FROM deliveries WHERE order_id=%s) LIMIT 1",
            (shipment_id, order_id),
        ).fetchone()
        if prior_handover:
            raise FulfilmentDispatchError("Legacy stock dispatch has already been handed over for this order")
    else:
        if order_status not in {"ready_for_dispatch", "dispatched"}:
            raise FulfilmentDispatchError("Order must be ready for dispatch before stock can be issued")
        requested = ({line.variant_id: line.quantity for line in dispatch_lines}
                     if dispatch_lines is not None else requested_from_packages)
        try:
            dispatched_lines = dispatch_order_stock(conn, order_id, requested)
        except ValueError as exc:
            raise FulfilmentDispatchError(str(exc)) from exc
        if dispatched_lines == 0:
            raise FulfilmentDispatchError("No outstanding reserved stock is available for this dispatch")

    if not legacy_preissued and not order_has_reservation(conn, order_id):
        cost_row = conn.execute("SELECT COALESCE(sum(total_cost),0) AS total_cost FROM inventory_order_issues WHERE order_id=%s", (order_id,)).fetchone()
        total_cost = Decimal(str(cost_row["total_cost"] or 0))
        if total_cost > 0:
            from app.api import accounting
            accounts = accounting._accounts_by_code(conn, ["1200", "5000"])
            accounting._post_voucher(
                conn,
                {"voucher_type": "journal", "voucher_date": accounting._today(),
                 "narration": f"Cost of goods sold for order {order_number}", "reference": order_number,
                 "party_type": "customer", "party_name": customer_name, "taxable_total": total_cost,
                 "total_amount": total_cost, "source_type": "order_fulfilment", "source_id": str(order_id),
                 "idempotency_key": f"order-fulfilment-cogs:{order_id}"},
                [{"account_id": accounts["5000"]["id"], "debit": total_cost, "credit": 0, "narration": "Cost of goods sold"},
                 {"account_id": accounts["1200"]["id"], "debit": 0, "credit": total_cost, "narration": "Inventory issued"}],
                (actor_id, actor_email),
            )
        if order_status != "dispatched":
            conn.execute("UPDATE orders SET status='dispatched',updated_at=now() WHERE id=%s", (order_id,))
            conn.execute("INSERT INTO order_status_history(order_id,from_status,to_status) VALUES(%s,%s,'dispatched')", (order_id, order_status))

    event = conn.execute(
        "INSERT INTO fulfilment_dispatch_events(shipment_id,dispatch_id,payload_hash,actor_user_id,actor_email,note) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
        (shipment_id, dispatch_id, payload_hash, actor_id, actor_email, note),
    ).fetchone()
    new_issues = conn.execute(
        "SELECT i.id,i.order_line_id,i.movement_id,ol.variant_id,i.quantity FROM inventory_order_issues i "
        "JOIN order_lines ol ON ol.id=i.order_line_id WHERE i.order_id=%s AND i.id>%s ORDER BY i.id",
        (order_id, max_issue_id),
    ).fetchall()
    if package_allocations:
        issue_remaining = {int(issue["id"]): Decimal(str(issue["quantity"])) for issue in new_issues}
        for allocation in package_allocations:
            remaining = allocation["quantity"]
            for issue in new_issues:
                issue_id = int(issue["id"])
                if int(issue["order_line_id"]) != allocation["order_line_id"] or int(issue["variant_id"]) != allocation["variant_id"]:
                    continue
                take = min(remaining, issue_remaining[issue_id])
                if take <= 0:
                    continue
                conn.execute(
                    "INSERT INTO fulfilment_dispatch_event_lines(dispatch_event_id,package_line_id,order_line_id,variant_id,inventory_movement_id,quantity) VALUES(%s,%s,%s,%s,%s,%s)",
                    (event["id"], allocation["package_line_id"], allocation["order_line_id"], allocation["variant_id"], issue["movement_id"], take),
                )
                issue_remaining[issue_id] -= take
                remaining -= take
                if remaining <= 0:
                    break
            if remaining > 0:
                raise FulfilmentDispatchError("Package-line quantities do not reconcile to the stock issues created for this dispatch", 409)
    else:
        for issue in new_issues:
            conn.execute(
                "INSERT INTO fulfilment_dispatch_event_lines(dispatch_event_id,order_line_id,variant_id,inventory_movement_id,quantity) VALUES(%s,%s,%s,%s,%s)",
                (event["id"], issue["order_line_id"], issue["variant_id"], issue["movement_id"], issue["quantity"]),
            )
    return {"duplicate": False, "history_note": note}
