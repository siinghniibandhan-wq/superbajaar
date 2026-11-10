from datetime import date
from decimal import Decimal

import pytest

from app.services.hr_statutory_payroll import (
    StatutoryPolicyError,
    calculate_component,
    calculate_statutory_payroll,
    select_effective_policy,
)


def policy(component, config, **overrides):
    return {
        "id": 7, "component": component, "status": "approved",
        "effective_from": date(2026, 4, 1), "effective_to": None,
        "policy_config": config, **overrides,
    }


def test_missing_or_unapproved_policy_blocks_selection():
    with pytest.raises(StatutoryPolicyError, match="exactly one approved policy"):
        select_effective_policy([], "pf", date(2026, 11, 1))


def test_effective_policy_selection_is_date_scoped():
    old = policy("pf", {"enabled": True}, effective_to=date(2026, 9, 30))
    new = policy("pf", {"enabled": False}, effective_from=date(2026, 10, 1), id=8)
    assert select_effective_policy([old, new], "pf", date(2026, 10, 1))["id"] == 8


def test_disabled_component_is_zero_without_assuming_a_rate():
    result = calculate_component("esi", policy("esi", {"enabled": False}), {})
    assert result["employee_amount"] == Decimal("0.00")
    assert result["employer_amount"] == Decimal("0.00")


def test_employee_and_employer_contributions_are_separate_and_capped():
    result = calculate_component("pf", policy("pf", {
        "enabled": True, "basis_key": "pf_wages", "wage_ceiling": "20000",
        "employee_rate": "12", "employer_rate": "13",
    }), {"pf_wages": "25000"})
    assert result["employee_amount"] == Decimal("2400.00")
    assert result["employer_amount"] == Decimal("2600.00")


def test_state_pt_uses_configured_slabs_not_a_hardcoded_state():
    result = calculate_component("pt", policy("pt", {
        "enabled": True, "basis_key": "gross",
        "slabs": [{"upper_limit": "15000", "monthly_amount": "0"},
                  {"upper_limit": None, "monthly_amount": "200"}],
    }), {"gross": "18000"})
    assert result["employee_amount"] == Decimal("200.00")


def test_tds_requires_explicit_reviewed_projection_amount():
    with pytest.raises(StatutoryPolicyError, match="requires the employee selected regime"):
        calculate_component("tds", policy("tds", {"enabled": True}), {"tds_regime": "new"})


def test_override_requires_authorisation_and_reason():
    p = policy("esi", {"enabled": True, "basis_key": "esi_wages",
                       "employee_rate": "1", "employer_rate": "3"})
    with pytest.raises(StatutoryPolicyError, match="authorisation and a reason"):
        calculate_component("esi", p, {"esi_wages": "10000",
                                       "overrides": {"esi": {"employee_amount": "50"}}})


def test_complete_result_keeps_employer_cost_out_of_employee_deductions():
    policies = [
        policy("pf", {"enabled": True, "basis_key": "wages", "employee_rate": "10", "employer_rate": "12"}),
        policy("esi", {"enabled": False}),
        policy("pt", {"enabled": False}),
        policy("tds", {"enabled": True, "monthly_amount": "500"}),
    ]
    result = calculate_statutory_payroll(policies, {"wages": "10000"}, date(2026, 11, 1))
    assert result["employee_deductions_total"] == Decimal("1500.00")
    assert result["employer_contributions_total"] == Decimal("1200.00")


def test_readiness_reports_missing_policy_components_without_guessing():
    from app.services.hr_statutory_payroll import assess_policy_readiness
    policies = [policy("pf", {"enabled": False})]
    result = assess_policy_readiness(policies, date(2026, 11, 1))
    assert result["ready"] is False
    assert result["missing_components"] == ["esi", "pt", "tds"]
    assert result["duplicate_components"] == []


def test_readiness_rejects_overlapping_approved_policies():
    from app.services.hr_statutory_payroll import assess_policy_readiness
    policies = [
        policy(component, {"enabled": False})
        for component in ("pf", "esi", "pt", "tds")
    ]
    policies.append(policy("pf", {"enabled": False}, id=8))
    result = assess_policy_readiness(policies, date(2026, 11, 1))
    assert result["ready"] is False
    assert result["duplicate_components"] == ["pf"]


def test_tds_projection_uses_approved_regime_slabs_and_remaining_months():
    result = calculate_component("tds", policy("tds", {
        "enabled": True,
        "regimes": {
            "new": {
                "months_remaining": 10,
                "cess_rate": "4",
                "tax_already_deducted": "15000",
                "slabs": [
                    {"lower_limit": "0", "upper_limit": "300000", "rate": "0"},
                    {"lower_limit": "300000", "upper_limit": "600000", "rate": "5"},
                    {"lower_limit": "600000", "upper_limit": None, "rate": "10"},
                ],
            }
        },
    }), {"gross": "100000", "tds_regime": "new"})
    assert result["employee_amount"] == Decimal("6300.00")

def test_employee_applicability_override_can_disable_component_without_changing_policy():
    result = calculate_component("pf", policy("pf", {
        "enabled": True, "basis_key": "basic", "employee_rate": "12", "employer_rate": "12"
    }), {"basic": "30000", "applicability": {"pf": False}})
    assert result["enabled"] is False
    assert result["employee_amount"] == Decimal("0.00")

def test_enabled_pf_policy_must_supply_both_contribution_rates():
    with pytest.raises(StatutoryPolicyError, match="explicit employee_rate and employer_rate"):
        calculate_component("pf", policy("pf", {"enabled": True, "basis_key": "basic"}), {"basic": "30000"})
def test_tds_rejects_missing_or_incomplete_slab_schedule():
    with pytest.raises(StatutoryPolicyError, match="at least one configured tax slab"):
        calculate_component("tds", policy("tds", {"enabled": True, "regimes": {"new": {"months_remaining": 12, "slabs": []}}}), {"gross": "100000", "tds_regime": "new"})
    with pytest.raises(StatutoryPolicyError, match="do not cover"):
        calculate_component("tds", policy("tds", {"enabled": True, "regimes": {"new": {"months_remaining": 12, "slabs": [{"lower_limit": "0", "upper_limit": "500000", "rate": "5"}]}}}), {"gross": "100000", "tds_regime": "new"})

def test_readiness_ignores_draft_future_and_expired_policy_versions():
    from app.services.hr_statutory_payroll import assess_policy_readiness
    policies = [
        policy("pf", {"enabled": False}, effective_from=date(2026, 1, 1), effective_to=date(2026, 9, 30)),
        policy("esi", {"enabled": False}, status="draft"),
        policy("pt", {"enabled": False}, effective_from=date(2026, 12, 1)),
        policy("tds", {"enabled": False}),
    ]
    result = assess_policy_readiness(policies, date(2026, 11, 1))
    assert result["ready"] is False
    assert result["missing_components"] == ["pf", "esi", "pt"]
    assert result["duplicate_components"] == []


def test_readiness_accepts_one_effective_disabled_policy_per_component():
    from app.services.hr_statutory_payroll import assess_policy_readiness
    policies = [policy(component, {"enabled": False}) for component in ("pf", "esi", "pt", "tds")]
    result = assess_policy_readiness(policies, date(2026, 11, 1))
    assert result == {"ready": True, "missing_components": [], "duplicate_components": []}


def test_calculation_components_are_keyed_by_component_for_api_contract():
    policies = [
        policy("pf", {"enabled": False}),
        policy("esi", {"enabled": False}),
        policy("pt", {"enabled": False}),
        policy("tds", {"enabled": False}),
    ]
    result = calculate_statutory_payroll(policies, {}, date(2026, 11, 1))
    assert set(result["components"]) == {"pf", "esi", "pt", "tds"}
    assert result["components"]["pf"]["enabled"] is False
