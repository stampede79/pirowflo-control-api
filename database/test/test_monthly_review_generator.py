from datetime import date
from types import SimpleNamespace

from monthly_review_generator import (
    _completion_metrics,
    _interval_work_metrics,
    _power_target_status,
    _weekly_completion_metrics,
)


def workout(day: int, status: str):
    return SimpleNamespace(
        scheduled_date=date(2026, 10, day),
        status=status,
    )


def october_workouts():
    return [
        workout(6, "completed"),
        workout(10, "missed"),
        workout(12, "missed"),
        workout(14, "missed"),
        workout(16, "completed"),
        workout(18, "completed"),
        workout(20, "completed"),
        workout(22, "completed"),
        workout(24, "completed"),
        workout(26, "completed"),
        workout(28, "completed"),
        workout(30, "completed"),
    ]


def test_completion_metrics():
    result = _completion_metrics(
        october_workouts(),
        as_of=date(2026, 10, 31),
    )

    assert result == {
        "planned": 12,
        "due": 12,
        "completed": 9,
        "missed": 3,
        "skipped": 0,
        "open": 0,
        "completion_percent": 75.0,
    }


def test_weekly_completion_metrics():
    result = _weekly_completion_metrics(
        october_workouts(),
        as_of=date(2026, 10, 31),
    )

    assert result == [
        {
            "week": "2026-W41",
            "planned": 2,
            "due": 2,
            "completed": 1,
            "missed": 1,
            "skipped": 0,
            "open": 0,
            "completion_percent": 50.0,
        },
        {
            "week": "2026-W42",
            "planned": 4,
            "due": 4,
            "completed": 2,
            "missed": 2,
            "skipped": 0,
            "open": 0,
            "completion_percent": 50.0,
        },
        {
            "week": "2026-W43",
            "planned": 3,
            "due": 3,
            "completed": 3,
            "missed": 0,
            "skipped": 0,
            "open": 0,
            "completion_percent": 100.0,
        },
        {
            "week": "2026-W44",
            "planned": 3,
            "due": 3,
            "completed": 3,
            "missed": 0,
            "skipped": 0,
            "open": 0,
            "completion_percent": 100.0,
        },
    ]

def test_completion_metrics_ignore_future_open_workouts():
    workouts = [
        SimpleNamespace(
            scheduled_date=date(2026, 11, 2),
            status="completed",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 4),
            status="completed",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 6),
            status="planned",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 17),
            status="planned",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 24),
            status="planned",
        ),
    ]

    result = _completion_metrics(
        workouts,
        as_of=date(2026, 11, 5),
    )

    assert result == {
        "planned": 5,
        "due": 2,
        "completed": 2,
        "missed": 0,
        "skipped": 0,
        "open": 3,
        "completion_percent": 100.0,
    }

def test_weekly_completion_keeps_future_weeks_open():
    workouts = [
        SimpleNamespace(
            scheduled_date=date(2026, 11, 2),
            status="completed",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 4),
            status="completed",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 17),
            status="planned",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 19),
            status="planned",
        ),
        SimpleNamespace(
            scheduled_date=date(2026, 11, 21),
            status="planned",
        ),
    ]

    result = _weekly_completion_metrics(
        workouts,
        as_of=date(2026, 11, 5),
    )

    assert result[0]["completed"] == 2
    assert result[0]["due"] == 2
    assert result[0]["completion_percent"] == 100.0

    assert result[1]["planned"] == 3
    assert result[1]["due"] == 0
    assert result[1]["open"] == 3
    assert result[1]["completion_percent"] is None

def test_power_target_status():
    assert (
        _power_target_status(
            107.3,
            105.0,
            110.0,
        )
        == "in_target"
    )

    assert (
        _power_target_status(
            104.3,
            105.0,
            110.0,
        )
        == "below_target"
    )

    assert (
        _power_target_status(
            111.0,
            105.0,
            110.0,
        )
        == "above_target"
    )

    assert (
        _power_target_status(
            None,
            105.0,
            110.0,
        )
        == "unknown"
    )


def test_interval_work_metrics():
    phases = [
        {
            "name": "work_1",
            "average_power": 136.4,
            "target_power_min": 135.0,
            "target_power_max": 145.0,
        },
        {
            "name": "recovery_1",
            "average_power": 98.5,
            "target_power_min": 90.0,
            "target_power_max": 100.0,
        },
        {
            "name": "work_2",
            "average_power": 131.7,
            "target_power_min": 135.0,
            "target_power_max": 145.0,
        },
        {
            "name": "recovery_2",
            "average_power": 98.7,
            "target_power_min": 90.0,
            "target_power_max": 100.0,
        },
    ]

    interval_recovery = [
        {
            "heart_rate_recovery_bpm": 10.3,
        },
        {
            "heart_rate_recovery_bpm": 9.4,
        },
    ]

    result = _interval_work_metrics(
        phases,
        interval_recovery,
    )

    assert result is not None
    assert result["repetitions"] == 2

    assert result["work_in_target"] == 1
    assert result["work_below_target"] == 1
    assert result["work_above_target"] == 0

    assert result["average_work_power"] == 134.1

    assert result["recovery_in_target"] == 2
    assert result["recovery_below_target"] == 0
    assert result["recovery_above_target"] == 0

    assert result["average_recovery_power"] == 98.6
    assert result["average_hr_recovery_bpm"] == 9.9