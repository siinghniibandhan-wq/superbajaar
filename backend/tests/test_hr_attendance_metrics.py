from datetime import datetime, timezone, timedelta

import pytest

from app.services.hr_attendance import calculate_shift_metrics, is_within_geofence


def test_shift_metrics_calculate_late_early_overtime_and_paid_work_minutes():
    result = calculate_shift_metrics(
        clock_in_at=datetime(2026, 11, 11, 9, 12, tzinfo=timezone.utc),
        clock_out_at=datetime(2026, 11, 11, 18, 25, tzinfo=timezone.utc),
        planned_start_at=datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc),
        planned_end_at=datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc),
        grace_minutes=10,
        break_minutes=60,
    )
    assert result == {
        "worked_minutes": 493,
        "late_minutes": 2,
        "early_departure_minutes": 0,
        "overtime_minutes": 25,
    }


def test_shift_metrics_support_open_sessions_without_fabricating_overtime():
    result = calculate_shift_metrics(
        clock_in_at=datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc),
        clock_out_at=None,
        planned_start_at=datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc),
        planned_end_at=datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc),
    )
    assert result["overtime_minutes"] == 0
    assert result["early_departure_minutes"] == 0


def test_shift_metrics_reject_naive_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_shift_metrics(
            clock_in_at=datetime(2026, 11, 11, 9, 0),
            clock_out_at=None,
            planned_start_at=datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc),
            planned_end_at=datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc),
        )


def test_geofence_uses_meters_and_accepts_boundary():
    assert is_within_geofence(
        latitude=25.6093, longitude=85.1376,
        center_latitude=25.6093, center_longitude=85.1376,
        radius_meters=150,
    )
    assert is_within_geofence(
        latitude=25.6093, longitude=85.1392,
        center_latitude=25.6093, center_longitude=85.1376,
        radius_meters=180,
    )


def test_geofence_rejects_outside_and_invalid_coordinates():
    assert not is_within_geofence(
        latitude=25.6093, longitude=85.1410,
        center_latitude=25.6093, center_longitude=85.1376,
        radius_meters=100,
    )
    with pytest.raises(ValueError, match="latitude"):
        is_within_geofence(
            latitude=91, longitude=85.0,
            center_latitude=25.0, center_longitude=85.0,
            radius_meters=100,
        )


def test_attendance_punch_requires_coordinate_pairs_and_accuracy_requires_gps():
    from pydantic import ValidationError
    from app.api.hr import PunchInput

    with pytest.raises(ValidationError, match="provided together"):
        PunchInput(punch_type="clock_in", latitude=25.6)
    with pytest.raises(ValidationError, match="requires GPS coordinates"):
        PunchInput(punch_type="clock_out", accuracy_meters=20)
    assert PunchInput(punch_type="clock_in", latitude=25.6, longitude=85.1).latitude == 25.6


def test_attendance_punch_rejects_out_of_range_coordinates():
    from pydantic import ValidationError
    from app.api.hr import PunchInput

    with pytest.raises(ValidationError):
        PunchInput(punch_type="clock_in", latitude=91, longitude=85)


def test_attendance_policy_rejects_enforcement_without_geofence():
    from pydantic import ValidationError
    from app.api.hr import AttendancePolicyInput

    with pytest.raises(ValidationError, match="requires geofencing to be enabled"):
        AttendancePolicyInput(
            establishment_id=1, geofence_enabled=False, geofence_enforced=True,
            effective_from="2026-11-01",
        )


def test_attendance_policy_rejects_reversed_effective_period():
    from pydantic import ValidationError
    from app.api.hr import AttendancePolicyInput

    with pytest.raises(ValidationError, match="end date cannot precede"):
        AttendancePolicyInput(
            establishment_id=1, effective_from="2026-11-30", effective_to="2026-11-01",
        )


def test_attendance_work_location_validates_coordinates_and_radius():
    from pydantic import ValidationError
    from app.api.hr import AttendanceWorkLocationInput

    with pytest.raises(ValidationError):
        AttendanceWorkLocationInput(
            establishment_id=1, code="HQ", name="Head Office",
            latitude=91, longitude=85.1, radius_meters=150,
        )
    with pytest.raises(ValidationError):
        AttendanceWorkLocationInput(
            establishment_id=1, code="HQ", name="Head Office",
            latitude=25.6, longitude=85.1, radius_meters=5,
        )
