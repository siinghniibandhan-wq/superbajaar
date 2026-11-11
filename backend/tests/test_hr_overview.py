import pytest

from app.services.hr_overview import month_period


def test_hr_overview_month_period_covers_complete_calendar_month():
    start, end = month_period("2026-11")
    assert start.isoformat() == "2026-11-01"
    assert end.isoformat() == "2026-12-01"


@pytest.mark.parametrize("value", ["2026-1", "2026-13", "2026-00", "26-11", "2026-11-01", ""])
def test_hr_overview_rejects_invalid_month(value):
    with pytest.raises(ValueError):
        month_period(value)


def test_hr_overview_month_period_handles_leap_february():
    start, end = month_period("2028-02")
    assert start.isoformat() == "2028-02-01"
    assert end.isoformat() == "2028-03-01"
