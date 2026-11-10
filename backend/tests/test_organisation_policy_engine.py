from decimal import Decimal

import pytest

from app.services.organisation_policy import (
    PolicyConfigurationError,
    evaluate_purchase_policy,
    validate_inventory_policy,
    validate_purchase_policy,
    resolve_minimum_remaining_shelf_life_days,
)


def valid_purchase_policy():
    return {
        "approval_bands": [
            {
                "min_amount": "0",
                "max_amount": "10000",
                "stages": [{"sequence": 1, "approver_roles": ["manager"]}],
            },
            {
                "min_amount": "10000",
                "max_amount": None,
                "stages": [
                    {"sequence": 1, "approver_roles": ["manager"]},
                    {"sequence": 2, "approver_roles": ["owner"]},
                ],
            },
        ]
    }


def test_purchase_policy_selects_configured_band_and_stages_without_code_defaults():
    result = evaluate_purchase_policy(valid_purchase_policy(), Decimal("15000"))
    assert [stage["sequence"] for stage in result["stages"]] == [1, 2]
    assert result["min_amount"] == "10000"
    assert result["max_amount"] is None


def test_purchase_policy_rejects_overlapping_amount_bands():
    config = valid_purchase_policy()
    config["approval_bands"][1]["min_amount"] = "9000"
    with pytest.raises(PolicyConfigurationError, match="overlap"):
        validate_purchase_policy(config)


def test_purchase_policy_fails_closed_when_amount_has_no_configured_band():
    config = valid_purchase_policy()
    config["approval_bands"] = [config["approval_bands"][0]]
    with pytest.raises(PolicyConfigurationError, match="No unique approval band"):
        evaluate_purchase_policy(config, Decimal("10000"))


def test_purchase_policy_rejects_non_contiguous_or_duplicate_stage_sequence():
    config = valid_purchase_policy()
    config["approval_bands"][1]["stages"][1]["sequence"] = 1
    with pytest.raises(PolicyConfigurationError, match="unique and contiguous"):
        validate_purchase_policy(config)


def test_inventory_policy_requires_configured_approver_stages_when_approval_is_required():
    with pytest.raises(PolicyConfigurationError, match="approval stages"):
        validate_inventory_policy({
            "event_policies": {
                "scrap": {"approval_required": True, "stages": []}
            }
        })



def test_shelf_life_resolution_uses_narrowest_configured_override():
    config = {
        "shelf_life": {
            "default_minimum_remaining_days": 5,
            "category_overrides": {"7": 8},
            "product_overrides": {"21": 12},
            "location_overrides": {"3": 15},
        }
    }
    assert resolve_minimum_remaining_shelf_life_days(config, location_id=3, product_id=21, category_id=7) == 15
    assert resolve_minimum_remaining_shelf_life_days(config, product_id=21, category_id=7) == 12
    assert resolve_minimum_remaining_shelf_life_days(config, category_id=7) == 8
    assert resolve_minimum_remaining_shelf_life_days(config) == 5


def test_shelf_life_requires_explicit_organisation_default_even_when_null():
    with pytest.raises(PolicyConfigurationError, match="explicit organisation shelf-life default"):
        resolve_minimum_remaining_shelf_life_days({"shelf_life": {}})


def test_shelf_life_rejects_negative_or_fractional_days():
    with pytest.raises(PolicyConfigurationError, match="non-negative whole number"):
        resolve_minimum_remaining_shelf_life_days({"shelf_life": {"default_minimum_remaining_days": -1}})


def test_inventory_policy_rejects_missing_approval_required_flag():
    with pytest.raises(PolicyConfigurationError, match="approval_required must be explicitly true or false"):
        validate_inventory_policy({
            "event_policies": {"issue": {}},
            "shelf_life": {"default_minimum_remaining_days": None},
        })


def test_inventory_policy_rejects_non_boolean_approval_required_flag():
    with pytest.raises(PolicyConfigurationError, match="approval_required must be explicitly true or false"):
        validate_inventory_policy({
            "event_policies": {"issue": {"approval_required": "false"}},
            "shelf_life": {"default_minimum_remaining_days": None},
        })


def test_inventory_policy_requires_unique_contiguous_approval_stages_and_roles():
    with pytest.raises(PolicyConfigurationError, match="unique and contiguous"):
        validate_inventory_policy({
            "event_policies": {
                "scrap": {
                    "approval_required": True,
                    "stages": [
                        {"sequence": 1, "approver_roles": ["manager"]},
                        {"sequence": 1, "approver_roles": ["owner"]},
                    ],
                }
            },
            "shelf_life": {"default_minimum_remaining_days": None},
        })


def test_inventory_policy_rejects_blank_approver_roles():
    with pytest.raises(PolicyConfigurationError, match="non-blank"):
        validate_inventory_policy({
            "event_policies": {
                "scrap": {
                    "approval_required": True,
                    "stages": [{"sequence": 1, "approver_roles": ["  "]}],
                }
            },
            "shelf_life": {"default_minimum_remaining_days": None},
        })


def test_supplier_invoice_variance_tolerance_is_explicit_and_amount_based():
    from app.services.organisation_policy import supplier_invoice_variance_within_tolerance
    config = {"supplier_invoice_variance_tolerance": {"amount": "25.00"}}
    assert supplier_invoice_variance_within_tolerance(config, Decimal("25.00")) is True
    assert supplier_invoice_variance_within_tolerance(config, Decimal("25.01")) is False


def test_supplier_invoice_variance_defaults_to_exact_match_not_an_assumed_tolerance():
    from app.services.organisation_policy import supplier_invoice_variance_within_tolerance
    assert supplier_invoice_variance_within_tolerance({}, Decimal("0.00")) is True
    assert supplier_invoice_variance_within_tolerance({}, Decimal("0.01")) is False


def test_supplier_invoice_variance_rejects_negative_or_malformed_tolerance():
    from app.services.organisation_policy import (
        PolicyConfigurationError, supplier_invoice_variance_within_tolerance,
    )
    with pytest.raises(PolicyConfigurationError, match="non-negative amount"):
        supplier_invoice_variance_within_tolerance(
            {"supplier_invoice_variance_tolerance": {"amount": "-1"}}, Decimal("0")
        )


def test_purchase_policy_rejects_invalid_invoice_variance_tolerance_before_activation():
    config = valid_purchase_policy()
    config["supplier_invoice_variance_tolerance"] = {"amount": "-0.01"}
    with pytest.raises(PolicyConfigurationError, match="non-negative amount"):
        validate_purchase_policy(config)


def test_inventory_policy_validates_quantity_and_value_thresholds_with_approval_stages():
    validate_inventory_policy({
        "event_policies": {
            "issue": {
                "approval_required": False,
                "approval_thresholds": {"quantity": "5", "value_inr": "1000.00"},
                "stages": [{"sequence": 1, "approver_roles": ["manager"]}],
            }
        },
        "shelf_life": {"default_minimum_remaining_days": None},
    })


def test_inventory_policy_rejects_threshold_without_approval_stages():
    with pytest.raises(PolicyConfigurationError, match="approval stages"):
        validate_inventory_policy({
            "event_policies": {
                "issue": {
                    "approval_required": False,
                    "approval_thresholds": {"quantity": 5},
                }
            },
            "shelf_life": {"default_minimum_remaining_days": None},
        })


def test_inventory_policy_rejects_negative_value_threshold():
    with pytest.raises(PolicyConfigurationError, match="non-negative finite number"):
        validate_inventory_policy({
            "event_policies": {
                "issue": {
                    "approval_required": False,
                    "approval_thresholds": {"value_inr": "-0.01"},
                    "stages": [{"sequence": 1, "approver_roles": ["manager"]}],
                }
            },
            "shelf_life": {"default_minimum_remaining_days": None},
        })
