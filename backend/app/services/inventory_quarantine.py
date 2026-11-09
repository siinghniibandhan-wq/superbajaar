"""Pure quantity rules for controlled release of quarantined inventory."""

from decimal import Decimal


def calculate_quarantine_release(quarantined_quantity, release_quantity):
    """Return the remaining quarantine and accepted quantity for a valid release."""
    quarantined = Decimal(str(quarantined_quantity))
    release = Decimal(str(release_quantity))
    if quarantined <= 0 or release <= 0:
        raise ValueError("Quarantine and release quantities must be greater than zero")
    if release > quarantined:
        raise ValueError("Release quantity exceeds the quarantined quantity")
    return {
        "remaining_quarantined": quarantined - release,
        "accepted_quantity": release,
    }


def plan_quarantine_transfer(layers, requested_quantity=None):
    """Allocate an expired-stock transfer across already FIFO/FEFO-ordered layers."""
    available_layers = []
    total_available = Decimal("0")
    for layer in layers:
        layer_id = int(layer["id"])
        remaining = Decimal(str(layer["remaining_quantity"]))
        if remaining < 0:
            raise ValueError("Expired layer remaining quantity cannot be negative")
        if remaining > 0:
            available_layers.append((layer_id, remaining))
            total_available += remaining
    if total_available <= 0:
        raise ValueError("No expired stock remains to quarantine")
    requested = total_available if requested_quantity is None else Decimal(str(requested_quantity))
    if requested <= 0:
        raise ValueError("Quarantine transfer quantity must be greater than zero")
    if requested > total_available:
        raise ValueError("Requested quantity exceeds available expired stock")
    remaining_to_allocate = requested
    allocations = []
    for layer_id, available in available_layers:
        if remaining_to_allocate <= 0:
            break
        take = min(available, remaining_to_allocate)
        allocations.append({"layer_id": layer_id, "quantity": take})
        remaining_to_allocate -= take
    return allocations


def split_releasable_layers(layers):
    """Separate remaining return layers eligible for saleable release from expired stock."""
    releasable = []
    expired_quantity = Decimal("0")
    for layer in layers:
        remaining = Decimal(str(layer["remaining_quantity"]))
        if remaining < 0:
            raise ValueError("Quarantine layer remaining quantity cannot be negative")
        if remaining == 0:
            continue
        if layer.get("is_releasable"):
            releasable.append(layer)
        else:
            expired_quantity += remaining
    return releasable, expired_quantity
