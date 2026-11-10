from datetime import date
from decimal import Decimal

import pytest

from app.services.accounting_posting import (
    PostingConfigurationError,
    build_payroll_accrual_lines,
    select_mapping,
)


DAY = date(2026, 11, 30)


def mapping(role, account_id, component=None, **overrides):
    return {
        "legal_entity_code": "DEFAULT", "source_module": "hr",
        "event_type": "payroll_accrual", "line_role": role,
        "tax_component": component, "account_id": account_id,
        "status": "approved", "effective_from": date(2026, 4, 1),
        "effective_to": None, **overrides,
    }


def test_mapping_requires_one_approved_effective_record():
    row = mapping("salary_expense", 6001)
    assert select_mapping([row], legal_entity_code="DEFAULT", source_module="hr",
        event_type="payroll_accrual", line_role="salary_expense", event_date=DAY)["account_id"] == 6001
    with pytest.raises(PostingConfigurationError, match="found 0"):
        select_mapping([], legal_entity_code="DEFAULT", source_module="hr",
            event_type="payroll_accrual", line_role="salary_expense", event_date=DAY)


def test_mapping_rejects_overlapping_approved_records():
    rows = [mapping("salary_expense", 6001), mapping("salary_expense", 6002)]
    with pytest.raises(PostingConfigurationError, match="found 2"):
        select_mapping(rows, legal_entity_code="DEFAULT", source_module="hr",
            event_type="payroll_accrual", line_role="salary_expense", event_date=DAY)


def test_payroll_journal_separates_employee_deductions_and_employer_costs():
    rows = [
        mapping("salary_expense", 6001),
        mapping("reimbursement_expense", 6002),
        mapping("salary_payable", 2300),
        mapping("manual_deduction_payable", 2310),
        mapping("employee_statutory_payable", 2320, "pf"),
        mapping("employer_statutory_expense", 6011, "pf"),
        mapping("employer_statutory_payable", 2330, "pf"),
    ]
    lines = build_payroll_accrual_lines(
        gross="10000", reimbursements="500", net_pay="9500", manual_deductions="200",
        statutory_employee={"pf": "800"}, statutory_employer={"pf": "600"},
        mappings=rows, legal_entity_code="DEFAULT", event_date=DAY,
    )
    assert sum(x["debit"] for x in lines) == Decimal("11100.00")
    assert sum(x["credit"] for x in lines) == Decimal("11100.00")
    assert next(x for x in lines if x["account_id"] == 6011)["debit"] == Decimal("600.00")
    assert next(x for x in lines if x["account_id"] == 2320)["credit"] == Decimal("800.00")


def test_payroll_journal_fails_closed_when_mapping_missing_or_unbalanced():
    with pytest.raises(PostingConfigurationError, match="found 0"):
        build_payroll_accrual_lines(
            gross="10000", reimbursements="0", net_pay="9000", manual_deductions="0",
            statutory_employee={"tds": "1000"}, statutory_employer={},
            mappings=[], legal_entity_code="DEFAULT", event_date=DAY,
        )
    with pytest.raises(PostingConfigurationError, match="does not balance"):
        build_payroll_accrual_lines(
            gross="10000", reimbursements="0", net_pay="8000", manual_deductions="0",
            statutory_employee={"tds": "1000"}, statutory_employer={},
            mappings=[], legal_entity_code="DEFAULT", event_date=DAY,
        )


def test_inventory_journal_requires_two_approved_distinct_account_mappings():
    from app.services.accounting_posting import build_inventory_mapping_lines
    day = date(2026, 11, 2)
    mappings = [
        {"legal_entity_code": "DEFAULT", "source_module": "inventory",
         "event_type": "inventory_adjustment", "line_role": "inventory_asset",
         "tax_component": None, "account_id": 1200, "status": "approved",
         "effective_from": date(2026, 4, 1), "effective_to": None},
        {"legal_entity_code": "DEFAULT", "source_module": "inventory",
         "event_type": "inventory_adjustment", "line_role": "opening_balance_equity",
         "tax_component": None, "account_id": 3900, "status": "approved",
         "effective_from": date(2026, 4, 1), "effective_to": None},
    ]
    lines = build_inventory_mapping_lines(
        amount="250.25", mappings=mappings, legal_entity_code="DEFAULT",
        event_type="inventory_adjustment", debit_role="inventory_asset",
        credit_role="opening_balance_equity", event_date=day, narration="Opening valuation",
    )
    assert lines[0]["account_id"] == 1200 and lines[0]["debit"] == Decimal("250.25")
    assert lines[1]["account_id"] == 3900 and lines[1]["credit"] == Decimal("250.25")
    with pytest.raises(PostingConfigurationError, match="found 0"):
        build_inventory_mapping_lines(
            amount="250.25", mappings=mappings[:1], legal_entity_code="DEFAULT",
            event_type="inventory_adjustment", debit_role="inventory_asset",
            credit_role="opening_balance_equity", event_date=day, narration="Opening valuation",
        )


def test_qc_acceptance_journal_uses_inventory_and_grni_mapping_roles():
    from app.services.accounting_posting import build_inventory_mapping_lines

    mappings = [
        {"legal_entity_code": "DEFAULT", "source_module": "inventory",
         "event_type": "qc_acceptance", "line_role": "inventory_asset",
         "tax_component": None, "account_id": 1200, "status": "approved",
         "effective_from": date(2026, 4, 1), "effective_to": None},
        {"legal_entity_code": "DEFAULT", "source_module": "inventory",
         "event_type": "qc_acceptance", "line_role": "grni_clearing",
         "tax_component": None, "account_id": 2100, "status": "approved",
         "effective_from": date(2026, 4, 1), "effective_to": None},
    ]
    lines = build_inventory_mapping_lines(
        amount=Decimal("37.50"), mappings=mappings, legal_entity_code="DEFAULT",
        event_type="qc_acceptance", debit_role="inventory_asset",
        credit_role="grni_clearing", event_date=DAY, narration="QC accepted GRN stock",
    )
    assert [(line["account_id"], line["debit"], line["credit"]) for line in lines] == [
        (1200, Decimal("37.50"), Decimal("0.00")),
        (2100, Decimal("0.00"), Decimal("37.50")),
    ]
