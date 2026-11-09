"""Validation helpers for POS tender intent attached to order creation."""

PAYMENT_METHODS = {"upi", "card", "netbanking", "cod", "wallet", "bank_transfer", "other"}


def validate_pos_tender(*, channel, method, checkout_idempotency_key):
    if method is None:
        return True
    if method not in PAYMENT_METHODS:
        raise ValueError("unsupported POS tender method")
    if channel != "pos":
        raise ValueError("a tender intent can only be attached to POS orders")
    if not checkout_idempotency_key or len(checkout_idempotency_key) < 8:
        raise ValueError("POS tender creation requires a checkout idempotency key")
    return True


def checkout_payload_for_hash(payload):
    """Preserve legacy checkout hashes unless a POS tender was explicitly supplied."""
    normalized = dict(payload)
    if normalized.get("pos_payment_method") is None:
        normalized.pop("pos_payment_method", None)
    return normalized
