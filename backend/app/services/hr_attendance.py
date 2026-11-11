"""Pure attendance calculations shared by HR reporting and payroll workflows."""
from __future__ import annotations

from datetime import datetime
from math import asin, cos, radians, sin, sqrt


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def calculate_shift_metrics(
    *,
    clock_in_at: datetime,
    clock_out_at: datetime | None,
    planned_start_at: datetime,
    planned_end_at: datetime,
    grace_minutes: int = 0,
    break_minutes: int = 0,
) -> dict[str, int]:
    """Return elapsed paid minutes and schedule deviations, without rounding."""
    values = {
        "clock_in_at": clock_in_at,
        "planned_start_at": planned_start_at,
        "planned_end_at": planned_end_at,
    }
    if clock_out_at is not None:
        values["clock_out_at"] = clock_out_at
    for field, value in values.items():
        _require_aware(value, field)
    if planned_end_at <= planned_start_at:
        raise ValueError("planned_end_at must be after planned_start_at")
    if clock_out_at is not None and clock_out_at < clock_in_at:
        raise ValueError("clock_out_at cannot be before clock_in_at")
    if grace_minutes < 0 or break_minutes < 0:
        raise ValueError("grace_minutes and break_minutes cannot be negative")

    effective_end = clock_out_at
    worked_minutes = 0
    early_departure = 0
    overtime = 0
    if effective_end is not None:
        worked_minutes = max(
            0, int((effective_end - clock_in_at).total_seconds() // 60) - break_minutes
        )
        early_departure = max(
            0, int((planned_end_at - effective_end).total_seconds() // 60)
        )
        overtime = max(
            0, int((effective_end - planned_end_at).total_seconds() // 60)
        )

    late = max(
        0,
        int((clock_in_at - planned_start_at).total_seconds() // 60) - grace_minutes,
    )
    return {
        "worked_minutes": worked_minutes,
        "late_minutes": late,
        "early_departure_minutes": early_departure,
        "overtime_minutes": overtime,
    }


def is_within_geofence(
    *,
    latitude: float,
    longitude: float,
    center_latitude: float,
    center_longitude: float,
    radius_meters: float,
) -> bool:
    """Check a GPS point against a circular geofence using haversine distance."""
    coordinates = (
        ("latitude", latitude, -90.0, 90.0),
        ("center_latitude", center_latitude, -90.0, 90.0),
        ("longitude", longitude, -180.0, 180.0),
        ("center_longitude", center_longitude, -180.0, 180.0),
    )
    for name, value, minimum, maximum in coordinates:
        if not minimum <= float(value) <= maximum:
            raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    if radius_meters <= 0:
        raise ValueError("radius_meters must be greater than zero")

    earth_radius_meters = 6_371_000
    lat1, lat2 = radians(latitude), radians(center_latitude)
    delta_lat = radians(center_latitude - latitude)
    delta_lon = radians(center_longitude - longitude)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    distance = 2 * earth_radius_meters * asin(sqrt(min(1.0, haversine)))
    return distance <= radius_meters
