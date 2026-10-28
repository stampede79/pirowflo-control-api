from datetime import date

from recovery_context import (
    build_recovery_context,
)


def sleep_record(
    record_date: str,
    *,
    sleep_seconds: int | None = 25200,
    score: int | None = 80,
    resting_hr: int | None = 50,
    hrv_status: str | None = "BALANCED",
    stress: int | None = 15,
) -> dict:
    return {
        "date": record_date,
        "total_sleep_seconds": sleep_seconds,
        "sleep_score_overall": score,
        "sleep_score_duration": "GOOD",
        "sleep_score_quality": "GOOD",
        "resting_heart_rate": resting_hr,
        "hrv_status": hrv_status,
        "avg_sleep_stress": stress,
    }


def test_build_recovery_context_calculates_baselines():
    records = [
        sleep_record(
            "2026-10-25",
            sleep_seconds=21600,
            score=70,
            resting_hr=48,
            stress=20,
        ),
        sleep_record(
            "2026-10-26",
            sleep_seconds=23400,
            score=75,
            resting_hr=46,
            stress=18,
        ),
        sleep_record(
            "2026-10-27",
            sleep_seconds=25200,
            score=80,
            resting_hr=44,
            stress=16,
        ),
        sleep_record(
            "2026-10-28",
            sleep_seconds=19800,
            score=65,
            resting_hr=47,
            hrv_status="LOW",
            stress=21,
        ),
    ]

    result = build_recovery_context(
        records,
        date(2026, 10, 28),
    )

    assert result is not None

    assert (
        result["sleep"]["duration_minutes"]
        == 330
    )

    assert (
        result["sleep"]["baseline_7d_minutes"]
        == 390.0
    )

    assert (
        result["sleep"]["deviation_minutes"]
        == -60.0
    )

    assert result["sleep"]["score"] == 65

    assert (
        result["sleep"]["score_baseline_7d"]
        == 75.0
    )

    assert (
        result["resting_heart_rate"]["bpm"]
        == 47
    )

    assert (
        result["resting_heart_rate"][
            "baseline_28d_bpm"
        ]
        == 46.0
    )

    assert (
        result["resting_heart_rate"][
            "deviation_bpm"
        ]
        == 1.0
    )

    assert result["hrv"]["status"] == "LOW"

    assert (
        result["sleep_stress"]["value"]
        == 21
    )

    assert (
        result["sleep_stress"]["baseline_7d"]
        == 18.0
    )

    assert (
        result["sleep_stress"]["deviation"]
        == 3.0
    )


def test_target_day_is_not_part_of_baseline():
    records = [
        sleep_record(
            "2026-10-27",
            sleep_seconds=25200,
            resting_hr=50,
        ),
        sleep_record(
            "2026-10-28",
            sleep_seconds=10800,
            resting_hr=80,
        ),
    ]

    result = build_recovery_context(
        records,
        date(2026, 10, 28),
    )

    assert result is not None

    assert (
        result["sleep"]["baseline_7d_minutes"]
        == 420.0
    )

    assert (
        result["resting_heart_rate"][
            "baseline_28d_bpm"
        ]
        == 50.0
    )


def test_missing_optional_values_are_supported():
    records = [
        sleep_record(
            "2026-10-27",
            sleep_seconds=25200,
            score=None,
            resting_hr=None,
            stress=None,
        ),
        sleep_record(
            "2026-10-28",
            sleep_seconds=21600,
            score=None,
            resting_hr=None,
            hrv_status=None,
            stress=None,
        ),
    ]

    result = build_recovery_context(
        records,
        date(2026, 10, 28),
    )

    assert result is not None

    assert result["sleep"]["score"] is None

    assert (
        result["sleep"]["score_baseline_7d"]
        is None
    )

    assert (
        result["resting_heart_rate"]["bpm"]
        is None
    )

    assert (
        result["resting_heart_rate"][
            "baseline_28d_bpm"
        ]
        is None
    )

    assert (
        result["resting_heart_rate"][
            "deviation_bpm"
        ]
        is None
    )

    assert result["hrv"]["status"] is None

    assert (
        result["sleep_stress"]["value"]
        is None
    )

    assert (
        result["sleep_stress"]["baseline_7d"]
        is None
    )


def test_missing_target_date_returns_none():
    records = [
        sleep_record("2026-10-27"),
        sleep_record("2026-10-26"),
    ]

    result = build_recovery_context(
        records,
        date(2026, 10, 28),
    )

    assert result is None


def test_seven_day_baseline_uses_calendar_window():
    records = [
        # Außerhalb des 7-Tage-Fensters.
        sleep_record(
            "2026-10-20",
            sleep_seconds=36000,
        ),
        sleep_record(
            "2026-10-22",
            sleep_seconds=21600,
        ),
        sleep_record(
            "2026-10-27",
            sleep_seconds=25200,
        ),
        sleep_record(
            "2026-10-28",
            sleep_seconds=19800,
        ),
    ]

    result = build_recovery_context(
        records,
        date(2026, 10, 28),
    )

    assert result is not None

    # Nur 22.10. und 27.10.:
    # (360 + 420) / 2 = 390 Minuten.
    assert (
        result["sleep"]["baseline_7d_minutes"]
        == 390.0
    )


def test_short_history_uses_available_records():
    records = [
        sleep_record(
            "2026-10-27",
            sleep_seconds=21600,
            resting_hr=48,
        ),
        sleep_record(
            "2026-10-28",
            sleep_seconds=19800,
            resting_hr=50,
        ),
    ]

    result = build_recovery_context(
        records,
        date(2026, 10, 28),
    )

    assert result is not None

    assert (
        result["sleep"]["baseline_7d_minutes"]
        == 360.0
    )

    assert (
        result["resting_heart_rate"][
            "baseline_28d_bpm"
        ]
        == 48.0
    )