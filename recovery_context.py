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

def build_recovery_summary(
    sleep_records: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    period_records = [
        record
        for record in sleep_records
        if (
            isinstance(record.get("date"), str)
            and start_date
            <= date.fromisoformat(record["date"])
            < end_date
        )
    ]

    baseline_start = (
        start_date - timedelta(days=28)
    )

    baseline_records = [
        record
        for record in sleep_records
        if (
            isinstance(record.get("date"), str)
            and baseline_start
            <= date.fromisoformat(record["date"])
            < start_date
        )
    ]

    sleep_average = _average(
        period_records,
        "total_sleep_seconds",
    )

    sleep_baseline = _average(
        baseline_records,
        "total_sleep_seconds",
    )

    score_average = _average(
        period_records,
        "sleep_score_overall",
    )

    score_baseline = _average(
        baseline_records,
        "sleep_score_overall",
    )

    resting_hr_average = _average(
        period_records,
        "resting_heart_rate",
    )

    resting_hr_baseline = _average(
        baseline_records,
        "resting_heart_rate",
    )

    stress_average = _average(
        period_records,
        "avg_sleep_stress",
    )

    stress_baseline = _average(
        baseline_records,
        "avg_sleep_stress",
    )

    hrv_statuses = [
        record.get("hrv_status")
        for record in period_records
        if record.get("hrv_status")
        is not None
    ]

    below_sleep_baseline_days = None

    if sleep_baseline is not None:
        below_sleep_baseline_days = sum(
            1
            for record in period_records
            if (
                isinstance(
                    record.get(
                        "total_sleep_seconds"
                    ),
                    (int, float),
                )
                and record[
                    "total_sleep_seconds"
                ] < sleep_baseline
            )
        )

    return {
        "start_date":
            start_date.isoformat(),
        "end_date":
            (
                end_date
                - timedelta(days=1)
            ).isoformat(),

        "days_with_data":
            len(period_records),

        "sleep": {
            "average_minutes": (
                _round_or_none(
                    sleep_average / 60
                )
                if sleep_average
                is not None
                else None
            ),
            "baseline_28d_minutes": (
                _round_or_none(
                    sleep_baseline / 60
                )
                if sleep_baseline
                is not None
                else None
            ),
            "deviation_minutes": (
                _round_or_none(
                    (
                        sleep_average
                        - sleep_baseline
                    )
                    / 60
                )
                if (
                    sleep_average
                    is not None
                    and sleep_baseline
                    is not None
                )
                else None
            ),
            "below_baseline_days":
                below_sleep_baseline_days,
        },

        "sleep_score": {
            "average":
                score_average,
            "baseline_28d":
                score_baseline,
            "deviation": (
                _round_or_none(
                    score_average
                    - score_baseline
                )
                if (
                    score_average is not None
                    and score_baseline
                    is not None
                )
                else None
            ),
        },

        "resting_heart_rate": {
            "average_bpm":
                resting_hr_average,
            "baseline_28d_bpm":
                resting_hr_baseline,
            "deviation_bpm": (
                _round_or_none(
                    resting_hr_average
                    - resting_hr_baseline
                )
                if (
                    resting_hr_average
                    is not None
                    and resting_hr_baseline
                    is not None
                )
                else None
            ),
        },

        "hrv": {
            "balanced_days":
                hrv_statuses.count(
                    "BALANCED"
                ),
            "unbalanced_days":
                hrv_statuses.count(
                    "UNBALANCED"
                ),
            "low_days":
                hrv_statuses.count(
                    "LOW"
                ),
            "days_with_status":
                len(hrv_statuses),
        },

        "sleep_stress": {
            "average":
                stress_average,
            "baseline_28d":
                stress_baseline,
            "deviation": (
                _round_or_none(
                    stress_average
                    - stress_baseline
                )
                if (
                    stress_average is not None
                    and stress_baseline
                    is not None
                )
                else None
            ),
        },
    }