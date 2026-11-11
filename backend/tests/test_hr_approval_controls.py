"""Maker-checker controls for HR financial and statutory approvals."""

import pytest
from fastapi import HTTPException

from app.api.hr import _require_independent_reviewer


def test_independent_reviewer_can_approve_another_managers_submission():
    _require_independent_reviewer(submitter_id=101, reviewer_id=202, record_name="Payroll")


def test_submitter_cannot_approve_their_own_financial_record():
    with pytest.raises(HTTPException) as error:
        _require_independent_reviewer(submitter_id=101, reviewer_id=101, record_name="Payroll")
    assert error.value.status_code == 403
    assert "different authorised user" in error.value.detail


def test_legacy_record_without_submitter_remains_reviewable():
    _require_independent_reviewer(submitter_id=None, reviewer_id=202, record_name="Salary revision")
