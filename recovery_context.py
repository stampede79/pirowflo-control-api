from datetime import date, timedelta
from statistics import mean
from typing import Any


def _average(
    records: list[dict[str, Any]],
    field: str,
) -> float | None:
    values = [
        float(record[field])
        for record in records
        if isinstance(
            record.get(field),
            (int, float),
        )
    ]

    if not values:
        return None

    return round(mean(values), 1)


def _round_or_none(
    value: float | None,
    digits: int = 1,
) -> float | None:
    if value is None:
        return None

    return round(value, digits)


def build_recovery_context(
    sleep_records: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any] | None:
    records = [
        record
        for record in sleep_records
        if isinstance(record.get("date"), str)
    ]

    records.sort(
        key=lambda record: record["date"]
    )

    target_record = next(
        (
            record
            for record in records
            if record["date"]
            == target_date.isoformat()
        ),
        None,
    )

    if target_record is None:
        return None

    previous = [
        record
        for record in records
        if (
            target_date - timedelta(days=28)
            <= date.fromisoformat(record["date"])
            < target_date
        )
    ]

    last_7 = [
        record
        for record in previous
        if (
            target_date - timedelta(days=7)
            <= date.fromisoformat(record["date"])
            < target_date
        )
    ]

    last_28 = [
        record
        for record in previous
        if (
            target_date - timedelta(days=28)
            <= date.fromisoformat(record["date"])
            < target_date
        )
    ]

    sleep_seconds = target_record.get(
        "total_sleep_seconds"
    )

    sleep_7d_seconds = _average(
        last_7,
        "total_sleep_seconds",
    )

    sleep_score = target_record.get(
        "sleep_score_overall"
    )

    sleep_score_7d = _average(
        last_7,
        "sleep_score_overall",
    )

    resting_hr = target_record.get(
        "resting_heart_rate"
    )

    resting_hr_28d = _average(
        last_28,
        "resting_heart_rate",
    )

    sleep_stress = target_record.get(
        "avg_sleep_stress"
    )

    sleep_stress_7d = _average(
        last_7,
        "avg_sleep_stress",
    )

    return {
        "date":
            target_date.isoformat(),

        "sleep": {
            "duration_minutes": (
                round(sleep_seconds / 60)
                if isinstance(
                    sleep_seconds,
                    (int, float),
                )
                else None
            ),
            "baseline_7d_minutes": (
                _round_or_none(
                    sleep_7d_seconds / 60,
                )
                if sleep_7d_seconds is not None
                else None
            ),
            "deviation_minutes": (
                _round_or_none(
                    (
                        sleep_seconds
                        - sleep_7d_seconds
                    )
                    / 60
                )
                if (
                    isinstance(
                        sleep_seconds,
                        (int, float),
                    )
                    and sleep_7d_seconds
                    is not None
                )
                else None
            ),
            "score":
                sleep_score,
            "score_baseline_7d":
                sleep_score_7d,
            "duration_rating":
                target_record.get(
                    "sleep_score_duration"
                ),
            "quality_rating":
                target_record.get(
                    "sleep_score_quality"
                ),
        },

        "resting_heart_rate": {
            "bpm":
                resting_hr,
            "baseline_28d_bpm":
                resting_hr_28d,
            "deviation_bpm": (
                _round_or_none(
                    resting_hr
                    - resting_hr_28d
                )
                if (
                    isinstance(
                        resting_hr,
                        (int, float),
                    )
                    and resting_hr_28d
                    is not None
                )
                else None
            ),
        },

        "hrv": {
            "status":
                target_record.get(
                    "hrv_status"
                ),
        },

        "sleep_stress": {
            "value":
                sleep_stress,
            "baseline_7d":
                sleep_stress_7d,
            "deviation": (
                _round_or_none(
                    sleep_stress
                    - sleep_stress_7d
                )
                if (
                    isinstance(
                        sleep_stress,
                        (int, float),
                    )
                    and sleep_stress_7d
                    is not None
                )
                else None
            ),
        },
    }