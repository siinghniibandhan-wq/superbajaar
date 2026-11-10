"""Deterministic evaluation for organisation-owned operational policies.

Policy values are supplied by persisted configuration. This module contains no
business thresholds, default approval roles or statutory/tax assumptions.
"""
from decimal import Decimal, InvalidOperation


class PolicyConfigurationError(ValueError):
    pass


def validate_purchase_policy(config: dict) -> None:
    if not isinstance(config, dict):
        raise PolicyConfigurationError("Purchase policy configuration must be an object")
    bands = config.get("approval_bands")
    if not isinstance(bands, list) or not bands:
        raise PolicyConfigurationError("Configure at least one approval band before activating this policy")
    parsed = []
    for band in bands:
        if not isinstance(band, dict):
            raise PolicyConfigurationError("Each approval band must be an object")
        try:
            lower = Decimal(str(band["min_amount"]))
            upper = None if band.get("max_amount") is None else Decimal(str(band["max_amount"]))
        except (KeyError, InvalidOperation, TypeError):
            raise PolicyConfigurationError("Each approval band needs valid min_amount and optional max_amount")
        if not lower.is_finite() or (upper is not None and not upper.is_finite()) or lower < 0 or (upper is not None and upper <= lower):
            raise PolicyConfigurationError("Approval band amount bounds are invalid")
        stages = band.get("stages")
        if not isinstance(stages, list) or not stages:
            raise PolicyConfigurationError("Each approval band needs at least one approval stage")
        sequences = []
        for stage in stages:
            if not isinstance(stage, dict) or not isinstance(stage.get("approver_roles"), list) or not stage["approver_roles"]:
                raise PolicyConfigurationError("Each approval stage needs configured approver_roles")
            if any(not isinstance(role, str) or not role.strip() for role in stage["approver_roles"]):
                raise PolicyConfigurationError("Approver roles must be non-blank strings")
            sequence = stage.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                raise PolicyConfigurationError("Each approval stage needs a positive sequence")
            sequences.append(sequence)
        if sorted(sequences) != list(range(1, len(sequences) + 1)):
            raise PolicyConfigurationError("Approval stage sequences must be unique and contiguous from 1")
        parsed.append((lower, upper))
    parsed.sort(key=lambda item: item[0])
    for previous, current in zip(parsed, parsed[1:]):
        if previous[1] is None or previous[1] > current[0]:
            raise PolicyConfigurationError("Approval bands overlap or are ambiguous")
    supplier_invoice_variance_within_tolerance(config, Decimal("0"))


def evaluate_purchase_policy(config: dict, amount: Decimal) -> dict:
    validate_purchase_policy(config)
    value = Decimal(str(amount))
    if not value.is_finite() or value < 0:
        raise PolicyConfigurationError("Purchase amount must be a finite non-negative value")
    matches = []
    for band in config["approval_bands"]:
        lower = Decimal(str(band["min_amount"]))
        upper = None if band.get("max_amount") is None else Decimal(str(band["max_amount"]))
        if value >= lower and (upper is None or value < upper):
            matches.append(band)
    if len(matches) != 1:
        raise PolicyConfigurationError("No unique approval band covers this purchase amount; update the organisation policy")
    band = matches[0]
    return {"min_amount": str(band["min_amount"]),
            "max_amount": None if band.get("max_amount") is None else str(band["max_amount"]),
            "stages": sorted(band["stages"], key=lambda item: item["sequence"])}


def validate_inventory_policy(config: dict) -> None:
    if not isinstance(config, dict) or not isinstance(config.get("event_policies"), dict) or not config["event_policies"]:
        raise PolicyConfigurationError("Configure event_policies before activating the inventory policy")
    for event, policy in config["event_policies"].items():
        if not isinstance(event, str) or not event.strip() or not isinstance(policy, dict):
            raise PolicyConfigurationError("Inventory event policies must be named configuration objects")
        approval_required = policy.get("approval_required")
        if not isinstance(approval_required, bool):
            raise PolicyConfigurationError(f"Inventory event '{event}': approval_required must be explicitly true or false")
        thresholds = policy.get("approval_thresholds")
        if thresholds is not None:
            if not isinstance(thresholds, dict) or not thresholds or not set(thresholds).issubset({"quantity", "value_inr"}):
                raise PolicyConfigurationError(f"Inventory event '{event}' approval_thresholds must contain quantity and/or value_inr")
            for key, value in thresholds.items():
                try:
                    threshold = Decimal(str(value))
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise PolicyConfigurationError(f"Inventory event '{event}' approval threshold '{key}' must be a non-negative finite number") from exc
                if not threshold.is_finite() or threshold < 0:
                    raise PolicyConfigurationError(f"Inventory event '{event}' approval threshold '{key}' must be a non-negative finite number")
        if approval_required or thresholds is not None:
            stages = policy.get("stages")
            if not isinstance(stages, list) or not stages:
                raise PolicyConfigurationError(f"Configure approval stages for inventory event '{event}'")
            sequences = []
            for stage in stages:
                if not isinstance(stage, dict) or not isinstance(stage.get("approver_roles"), list) or not stage["approver_roles"]:
                    raise PolicyConfigurationError(f"Configure approver_roles for inventory event '{event}'")
                if any(not isinstance(role, str) or not role.strip() for role in stage["approver_roles"]):
                    raise PolicyConfigurationError(f"Inventory event '{event}' approver roles must be non-blank strings")
                sequence = stage.get("sequence")
                if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                    raise PolicyConfigurationError(f"Inventory event '{event}' stages need positive integer sequences")
                sequences.append(sequence)
            if sorted(sequences) != list(range(1, len(sequences) + 1)):
                raise PolicyConfigurationError(f"Inventory event '{event}' approval stage sequences must be unique and contiguous from 1")
    resolve_minimum_remaining_shelf_life_days(config)


def supplier_invoice_variance_within_tolerance(config: dict, variance_amount: Decimal) -> bool:
    """Apply an explicitly configured INR tolerance; absent configuration means exact match."""
    raw = config.get("supplier_invoice_variance_tolerance") if isinstance(config, dict) else None
    tolerance = Decimal("0")
    if raw is not None:
        if not isinstance(raw, dict) or "amount" not in raw:
            raise PolicyConfigurationError("supplier_invoice_variance_tolerance must contain a non-negative amount in INR")
        try:
            tolerance = Decimal(str(raw["amount"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PolicyConfigurationError("supplier_invoice_variance_tolerance must contain a non-negative amount in INR") from exc
        if not tolerance.is_finite() or tolerance < 0:
            raise PolicyConfigurationError("supplier_invoice_variance_tolerance must contain a non-negative amount in INR")
    variance = Decimal(str(variance_amount))
    if not variance.is_finite():
        raise PolicyConfigurationError("Supplier invoice variance must be a finite amount")
    return abs(variance) <= tolerance


def resolve_minimum_remaining_shelf_life_days(config: dict, *, location_id: int | None = None,
                                               product_id: int | None = None,
                                               category_id: int | None = None) -> int | None:
    """Resolve shelf-life policy using location > product > category > organisation precedence."""
    shelf = config.get("shelf_life") if isinstance(config, dict) else None
    if not isinstance(shelf, dict) or "default_minimum_remaining_days" not in shelf:
        raise PolicyConfigurationError("Configure an explicit organisation shelf-life default (use null to disable a default minimum)")
    def read_days(value, label):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PolicyConfigurationError(f"{label} must be a non-negative whole number of days or null")
        return value
    for key, identifier in (("location_overrides", location_id), ("product_overrides", product_id), ("category_overrides", category_id)):
        mapping = shelf.get(key, {})
        if mapping is not None and not isinstance(mapping, dict):
            raise PolicyConfigurationError(f"{key} must be an object keyed by record ID")
        if identifier is not None and str(identifier) in (mapping or {}):
            return read_days(mapping[str(identifier)], f"{key}[{identifier}]")
    return read_days(shelf["default_minimum_remaining_days"], "default_minimum_remaining_days")
