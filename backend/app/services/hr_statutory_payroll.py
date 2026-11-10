"""Policy-driven statutory payroll calculations.

This module intentionally contains no jurisdiction-specific statutory rates.
Only approved, effective policy configurations supplied by the caller are used.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

MONEY = Decimal("0.01")
COMPONENTS = ("pf", "esi", "pt", "tds")


class StatutoryPolicyError(ValueError):
    """Raised when a statutory calculation lacks a valid approved policy."""


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def select_effective_policy(policies: list[dict[str, Any]], component: str, as_of: date) -> dict[str, Any]:
    if component not in COMPONENTS:
        raise StatutoryPolicyError(f"Unsupported statutory component: {component}")
    matches = [
        policy for policy in policies
        if policy.get("component") == component and policy.get("status") == "approved"
        and policy.get("effective_from") <= as_of
        and (policy.get("effective_to") is None or policy["effective_to"] >= as_of)
    ]
    if len(matches) != 1:
        raise StatutoryPolicyError(f"{component.upper()} requires exactly one approved policy effective on {as_of.isoformat()}")
    return matches[0]


def _amount(base: Decimal, config: dict[str, Any], side: str) -> Decimal:
    rate = Decimal(str(config.get(f"{side}_rate", "0")))
    if rate < 0:
        raise StatutoryPolicyError("Contribution rates cannot be negative")
    cap = config.get("wage_ceiling")
    eligible = min(base, Decimal(str(cap))) if cap is not None else base
    fixed = Decimal(str(config.get(f"{side}_fixed_amount", "0")))
    result = eligible * rate / Decimal("100") + fixed
    maximum = config.get(f"{side}_maximum")
    if maximum is not None:
        result = min(result, Decimal(str(maximum)))
    return money(max(result, Decimal("0")))


def calculate_component(component: str, policy: dict[str, Any], employee_inputs: dict[str, Any]) -> dict[str, Any]:
    """Return employee and employer amounts plus transparent calculation details."""
    config = policy.get("policy_config") or {}
    if (employee_inputs.get("applicability") or {}).get(component) is False:
        return {"component": component, "employee_amount": money(0), "employer_amount": money(0),
                "enabled": False, "policy_version_id": policy.get("id"),
                "details": {"reason": "employee_applicability_override"}}
    if not config.get("enabled", False):
        return {"component": component, "employee_amount": money(0), "employer_amount": money(0),
                "enabled": False, "policy_version_id": policy.get("id")}
    if component == "pt":
        amount = config.get("monthly_amount")
        if amount is None:
            gross = Decimal(str(employee_inputs.get(config.get("basis_key", "gross"), 0)))
            slabs = config.get("slabs") or []
            selected = next((slab for slab in slabs if slab.get("upper_limit") is None or gross <= Decimal(str(slab["upper_limit"]))), None)
            if selected is None:
                raise StatutoryPolicyError("PT policy has no matching slab")
            amount = selected.get("monthly_amount")
        if amount is None:
            raise StatutoryPolicyError("PT policy is missing monthly_amount")
        employee_amount, employer_amount = money(amount), money(0)
        details = {"monthly_amount": str(employee_amount)}
    elif component == "tds":
        regime = employee_inputs.get("tds_regime")
        regime_config = (config.get("regimes") or {}).get(regime) if regime else None
        if regime_config is not None:
            months_remaining = int(regime_config.get("months_remaining", 0))
            if not 1 <= months_remaining <= 12:
                raise StatutoryPolicyError("TDS months_remaining must be between 1 and 12")
            projected_income = employee_inputs.get("projected_annual_taxable_income")
            annual_income = Decimal(str(projected_income if projected_income is not None else Decimal(str(employee_inputs.get("annualized_gross", employee_inputs.get("gross", 0)))) * Decimal("12")))
            annual_income += Decimal(str((employee_inputs.get("previous_employer_income") or {}).get("taxable_income", 0)))
            if annual_income < 0:
                raise StatutoryPolicyError("Projected annual taxable income cannot be negative")
            declared = employee_inputs.get("declarations") or {}
            eligible_deductions = Decimal("0")
            for key, cap in (regime_config.get("declaration_deductions") or {}).items():
                eligible_deductions += min(max(Decimal(str(declared.get(key, 0))), Decimal("0")), Decimal(str(cap)))
            standard_deduction = Decimal(str(regime_config.get("standard_deduction", "0")))
            taxable_income = max(annual_income - eligible_deductions - standard_deduction, Decimal("0"))
            slabs = regime_config.get("slabs") or []
            if not slabs:
                raise StatutoryPolicyError("TDS regime requires at least one configured tax slab")
            tax, previous_upper = Decimal("0"), Decimal("0")
            for slab in slabs:
                lower = Decimal(str(slab.get("lower_limit", previous_upper)))
                upper_value = slab.get("upper_limit")
                upper = Decimal(str(upper_value)) if upper_value is not None else taxable_income
                if lower < previous_upper or upper < lower:
                    raise StatutoryPolicyError("TDS tax slabs must be ordered and non-overlapping")
                slab_income = max(min(taxable_income, upper) - lower, Decimal("0"))
                rate = Decimal(str(slab.get("rate", "0")))
                if rate < 0:
                    raise StatutoryPolicyError("TDS slab rates cannot be negative")
                tax += slab_income * rate / Decimal("100")
                previous_upper = upper
                if upper_value is None or taxable_income <= upper:
                    break
            if previous_upper < taxable_income:
                raise StatutoryPolicyError("TDS tax slabs do not cover the projected taxable income")
            rebate_limit = regime_config.get("rebate_income_limit")
            if rebate_limit is not None and taxable_income <= Decimal(str(rebate_limit)):
                tax = max(tax - Decimal(str(regime_config.get("rebate_amount", "0"))), Decimal("0"))
            cess_rate = Decimal(str(regime_config.get("cess_rate", "0")))
            if cess_rate < 0:
                raise StatutoryPolicyError("TDS cess rate cannot be negative")
            tax += tax * cess_rate / Decimal("100")
            already_deducted = Decimal(str(regime_config.get("tax_already_deducted", "0"))) + Decimal(str((employee_inputs.get("previous_employer_income") or {}).get("tax_deducted", 0)))
            if already_deducted < 0:
                raise StatutoryPolicyError("Tax already deducted cannot be negative")
            annual_balance = max(tax - already_deducted, Decimal("0"))
            employee_amount = money(annual_balance / Decimal(months_remaining))
            details = {"tax_regime": regime, "annual_income": str(annual_income),
                       "eligible_declaration_deductions": str(eligible_deductions),
                       "standard_deduction": str(standard_deduction), "taxable_income": str(taxable_income),
                       "projected_annual_tax": str(money(tax)), "tax_already_deducted": str(already_deducted),
                       "months_remaining": months_remaining}
        elif "monthly_amount" in config:
            employee_amount = money(config["monthly_amount"])
            details = {"monthly_amount": str(employee_amount), "tax_regime": regime}
        else:
            raise StatutoryPolicyError("TDS policy requires the employee selected regime and reviewed slab configuration")
        employer_amount = money(0)
    else:
        basis_key = config.get("basis_key")
        if not basis_key:
            raise StatutoryPolicyError(f"{component.upper()} policy requires basis_key")
        if "employee_rate" not in config or "employer_rate" not in config:
            raise StatutoryPolicyError(f"{component.upper()} policy requires explicit employee_rate and employer_rate")
        base = Decimal(str(employee_inputs.get(basis_key, 0)))
        employee_amount, employer_amount = _amount(base, config, "employee"), _amount(base, config, "employer")
        details = {"basis_key": basis_key, "basis_amount": str(base), "wage_ceiling": config.get("wage_ceiling")}
    override = (employee_inputs.get("overrides") or {}).get(component)
    if override is not None:
        if not override.get("authorised") or not str(override.get("reason", "")).strip():
            raise StatutoryPolicyError("A statutory override requires authorisation and a reason")
        if "employee_amount" in override:
            employee_amount = money(override["employee_amount"])
        if "employer_amount" in override:
            employer_amount = money(override["employer_amount"])
        details["override_reason"] = override["reason"]
        details["override_actor_id"] = override.get("actor_id")
    if employee_amount < 0 or employer_amount < 0:
        raise StatutoryPolicyError("Statutory amounts cannot be negative")
    return {"component": component, "employee_amount": employee_amount, "employer_amount": employer_amount,
            "enabled": True, "policy_version_id": policy.get("id"), "details": details}


def calculate_statutory_payroll(policies: list[dict[str, Any]], employee_inputs: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Calculate each component using exactly one effective approved policy."""
    results = []
    missing = []
    duplicates = []
    for component in COMPONENTS:
        applicable = (employee_inputs.get("applicability") or {}).get(component) is not False
        if not applicable:
            results.append({"component": component, "employee_amount": money(0), "employer_amount": money(0), "enabled": False})
            continue
        matches = [p for p in policies if p.get("component") == component and p.get("status") == "approved"
                   and p.get("effective_from") <= as_of and (p.get("effective_to") is None or p["effective_to"] >= as_of)]
        if len(matches) == 0:
            missing.append(component)
            continue
        if len(matches) > 1:
            duplicates.append(component)
            continue
        results.append(calculate_component(component, matches[0], employee_inputs))
    employee_total = money(sum((item["employee_amount"] for item in results), Decimal("0")))
    employer_total = money(sum((item["employer_amount"] for item in results), Decimal("0")))
    return {
        "components": results,
        "missing_components": missing,
        "duplicate_components": duplicates,
        "employee_deductions_total": employee_total,
        "employer_contributions_total": employer_total,
    }


def assess_policy_readiness(policies: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    """Check that each statutory component has exactly one approved effective policy.

    Disabled policies count as configured: a business may explicitly configure a
    component as disabled. Missing, draft, future, expired, or overlapping policy
    versions never count as ready.
    """
    missing: list[str] = []
    duplicates: list[str] = []
    for component in COMPONENTS:
        matches = [
            policy for policy in policies
            if policy.get("component") == component
            and policy.get("status") == "approved"
            and policy.get("effective_from") is not None
            and policy["effective_from"] <= as_of
            and (policy.get("effective_to") is None or policy["effective_to"] >= as_of)
        ]
        if not matches:
            missing.append(component)
        elif len(matches) > 1:
            duplicates.append(component)
    return {
        "ready": not missing and not duplicates,
        "missing_components": missing,
        "duplicate_components": duplicates,
    }
