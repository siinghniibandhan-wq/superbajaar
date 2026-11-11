"""Period helpers and authoritative HR overview aggregation.

The overview intentionally reports unsupported attendance classifications as unavailable:
a punch without an assigned published shift and approved holiday/leave context cannot
prove that another employee was absent or late.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date


_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def month_period(value: str) -> tuple[date, date]:
    """Return the half-open [first day, first day of next month) period."""
    if not isinstance(value, str) or not _MONTH_PATTERN.fullmatch(value):
        raise ValueError("Month must use YYYY-MM format")
    year, month = (int(part) for part in value.split("-"))
    if year < 2000 or year > 2200:
        raise ValueError("Month year must be between 2000 and 2200")
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def month_trend_period(value: str, months: int = 6) -> tuple[date, date]:
    """Return a bounded month-aligned period ending after the selected month."""
    start, end = month_period(value)
    first_index = start.year * 12 + start.month - months
    first_year, first_month_zero = divmod(first_index, 12)
    return date(first_year, first_month_zero + 1, 1), end
