"""Shared, configuration-driven Accounting posting primitives.

This module is intentionally free of database/network side effects so event
builders and mapping selection can be unit-tested before wiring into workflows.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CENT = Decimal("0.01")


class PostingConfigurationError(ValueError):
    """Raised when an approved account mapping is missing or ambiguous."""


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def resolve_legal_entity_code(establishment_code: Any) -> str:
    """Resolve the accounting mapping scope for a stock facility."""
    if establishment_code is None:
        return "DEFAULT"
    if not isinstance(establishment_code, str):
        raise ValueError("Legal establishment code must be a string")
    value = establishment_code.strip()
    return value or "DEFAULT"


def select_mapping(mappings: list[dict[str, Any]], *, legal_entity_code: str,
                   source_module: str, event_type: str, line_role: str,
                   event_date: date, tax_component: str | None = None) -> dict[str, Any]:
    """Resolve exactly one approved mapping effective on event_date."""
    matches = [
        item for item in mappings
        if item.get("legal_entity_code") == legal_entity_code
        and item.get("source_module") == source_module
        and item.get("event_type") == event_type
        and item.get("line_role") == line_role
        and item.get("tax_component") == tax_component
        and item.get("status") == "approved"
        and item.get("effective_from") <= event_date
        and (item.get("effective_to") is None or item["effective_to"] >= event_date)
    ]
    if len(matches) != 1:
        raise PostingConfigurationError(
            f"Expected exactly one approved mapping for {source_module}/{event_type}/{line_role}"
            f"/{tax_component or 'none'} on {event_date.isoformat()}, found {len(matches)}"
        )
    account_id = matches[0].get("account_id")
    if not isinstance(account_id, int) or account_id <= 0:
        raise PostingConfigurationError("Approved mapping has an invalid account_id")
    return matches[0]


def build_payroll_accrual_lines(*, gross: Any, reimbursements: Any, net_pay: Any,
                                manual_deductions: Any, statutory_employee: dict[str, Any],
                                statutory_employer: dict[str, Any], mappings: list[dict[str, Any]],
                                legal_entity_code: str, event_date: date) -> list[dict[str, Any]]:
    """Build balanced payroll-accrual lines using only explicit approved mappings."""
    gross_amount, reimbursement_amount = money(gross), money(reimbursements)
    net_amount, manual_amount = money(net_pay), money(manual_deductions)
    if min(gross_amount, reimbursement_amount, net_amount, manual_amount) < 0:
        raise PostingConfigurationError("Payroll amounts cannot be negative")
    employee_components = {key: money(value) for key, value in statutory_employee.items()}
    employer_components = {key: money(value) for key, value in statutory_employer.items()}
    components = set(employee_components) | set(employer_components)
    if components - {"pf", "esi", "pt", "tds"}:
        raise PostingConfigurationError("Unsupported statutory payroll component")
    if any(v < 0 for v in (*employee_components.values(), *employer_components.values())):
        raise PostingConfigurationError("Statutory amounts cannot be negative")
    expected_credit = net_amount + manual_amount + sum(employee_components.values(), money(0)) + sum(employer_components.values(), money(0))
    expected_debit = gross_amount + reimbursement_amount + sum(employer_components.values(), money(0))
    if expected_debit != expected_credit:
        raise PostingConfigurationError(f"Payroll accrual does not balance: debit {expected_debit}, credit {expected_credit}")

    def mapping(role: str, component: str | None = None) -> int:
        return select_mapping(mappings, legal_entity_code=legal_entity_code, source_module="hr",
                              event_type="payroll_accrual", line_role=role, event_date=event_date,
                              tax_component=component)["account_id"]
    lines: list[dict[str, Any]] = []
    def add(role: str, amount: Decimal, side: str, component: str | None = None) -> None:
        if amount <= 0:
            return
        lines.append({"account_id": mapping(role, component),
                      "debit": amount if side == "debit" else money(0),
                      "credit": amount if side == "credit" else money(0),
                      "narration": f"Payroll {role.replace('_', ' ')}" + (f" ({component.upper()})" if component else "")})
    add("salary_expense", gross_amount, "debit")
    add("reimbursement_expense", reimbursement_amount, "debit")
    add("salary_payable", net_amount, "credit")
    add("manual_deduction_payable", manual_amount, "credit")
    for component in sorted(components):
        add("employee_statutory_payable", employee_components.get(component, money(0)), "credit", component)
        add("employer_statutory_expense", employer_components.get(component, money(0)), "debit", component)
        add("employer_statutory_payable", employer_components.get(component, money(0)), "credit", component)
    debit = sum((line["debit"] for line in lines), money(0))
    credit = sum((line["credit"] for line in lines), money(0))
    if len(lines) < 2 or debit != credit:
        raise PostingConfigurationError("Generated payroll journal is not balanced")
    return lines


def build_supplier_invoice_mapping_lines(invoice: dict[str, Any], mappings: list[dict[str, Any]],
                                         *, legal_entity_code: str, event_date: date) -> list[dict[str, Any]]:
    """Build a matched supplier-invoice voucher from Finance-approved mappings."""
    if money(invoice.get("cess_amount")) != 0:
        raise PostingConfigurationError("Supplier invoice cess requires a configured input-cess ledger role; approval is blocked")
    grni = money(money(invoice.get("taxable_value")) + money(invoice.get("freight_amount")) - money(invoice.get("discount_amount")))
    invoice_total = money(invoice.get("invoice_total"))
    if grni <= 0 or invoice_total <= 0:
        raise PostingConfigurationError("Net GRNI and invoice total must be positive")
    def account(role: str, component: str | None = None) -> int:
        return select_mapping(mappings, legal_entity_code=legal_entity_code, source_module="purchasing",
                              event_type="supplier_invoice_approval", line_role=role,
                              event_date=event_date, tax_component=component)["account_id"]
    lines = [{"account_id": account("grni_clearing"), "debit": grni, "credit": money(0),
              "narration": "Clear goods received not invoiced"}]
    for field, component, narration in (("cgst_amount", "cgst", "Input CGST"),
                                        ("sgst_amount", "sgst", "Input SGST"),
                                        ("igst_amount", "igst", "Input IGST")):
        amount = money(invoice.get(field))
        if amount:
            lines.append({"account_id": account("input_tax", component), "debit": amount,
                          "credit": money(0), "narration": narration})
    lines.append({"account_id": account("accounts_payable"), "debit": money(0),
                  "credit": invoice_total, "narration": "Supplier accounts payable"})
    debit = sum((line["debit"] for line in lines), money(0))
    credit = sum((line["credit"] for line in lines), money(0))
    if debit != credit:
        raise PostingConfigurationError(f"Supplier invoice journal does not balance: debit {debit}, credit {credit}")
    return lines


def build_inventory_mapping_lines(*, amount: Any, mappings: list[dict[str, Any]],
                                  legal_entity_code: str, event_type: str, debit_role: str,
                                  credit_role: str, event_date: date, narration: str) -> list[dict[str, Any]]:
    """Build a balanced two-sided inventory journal from approved account roles."""
    value = money(amount)
    if value <= 0:
        raise PostingConfigurationError("Inventory journal amount must be positive")
    def account(role: str) -> int:
        return select_mapping(mappings, legal_entity_code=legal_entity_code, source_module="inventory",
                              event_type=event_type, line_role=role, event_date=event_date)["account_id"]
    debit_account, credit_account = account(debit_role), account(credit_role)
    if debit_account == credit_account:
        raise PostingConfigurationError("Inventory debit and credit mappings must use different ledger accounts")
    return [{"account_id": debit_account, "debit": value, "credit": money(0), "narration": narration},
            {"account_id": credit_account, "debit": money(0), "credit": value, "narration": narration}]
