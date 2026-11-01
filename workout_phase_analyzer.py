from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any
from statistics import mean, pstdev


def _parse_duration(value: str | None) -> int:
    if not value:
        return 0

    value = value.strip().lower()

    if value.endswith("m"):
        return int(value[:-1]) * 60

    if value.endswith("s"):
        return int(value[:-1])

    raise ValueError(
        f"Unsupported duration: {value}"
    )


def _phase_duration(
    definition: str | None,
) -> int:
    if not definition:
        return 0

    duration = definition.split(
        ",",
        1,
    )[0]

    return _parse_duration(duration)


def _target_power(
    definition: str | None,
) -> tuple[float, float] | None:
    if not definition:
        return None

    for part in definition.split(","):
        part = part.strip().lower()

        if not part.endswith("w"):
            continue

        value = part[:-1]

        if "-" not in value:
            try:
                power = float(value)

                return power, power
            except ValueError:
                continue

        low, high = value.split(
            "-",
            1,
        )

        try:
            return float(low), float(high)
        except ValueError:
            continue

    return None


def _values_for_range(
    points: list[dict[str, Any]],
    stream_start: datetime,
    start_seconds: int,
    end_seconds: int,
) -> list[float]:
    values = []

    for point in points:
        elapsed = (
            point["time"] - stream_start
        ).total_seconds()

        if (
            elapsed >= start_seconds
            and elapsed < end_seconds
        ):
            values.append(
                float(point["value"])
            )

    return values


def _average(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return round(
        mean(values),
        1,
    )

def _average_for_range(
    points: list[dict[str, Any]],
    stream_start: datetime,
    start_seconds: int,
    end_seconds: int,
) -> float | None:
    return _average(
        _values_for_range(
            points,
            stream_start,
            start_seconds,
            end_seconds,
        )
    )


def _max_rolling_average(
    values: list[float],
    window_size: int = 5,
) -> float | None:
    if not values:
        return None

    if len(values) < window_size:
        return _average(values)

    averages = [
        mean(
            values[
                index:index + window_size
            ]
        )
        for index in range(
            len(values) - window_size + 1
        )
    ]

    return round(max(averages), 1)

def _split_half(
    values: list[float],
) -> tuple[list[float], list[float]]:
    midpoint = len(values) // 2

    return (
        values[:midpoint],
        values[midpoint:],
    )

def _power_trend(
    change_percent: float | None,
) -> str:
    if change_percent is None:
        return "unknown"

    if change_percent > 5.0:
        return "rising"

    if change_percent < -5.0:
        return "falling"

    return "stable"


def _heart_rate_trend(
    change_bpm: float | None,
) -> str:
    if change_bpm is None:
        return "unknown"

    if change_bpm > 3.0:
        return "rising"

    if change_bpm < -3.0:
        return "falling"

    return "stable"

def _phase_metrics(
    *,
    name: str,
    start_seconds: int,
    end_seconds: int,
    stream_start: datetime,
    streams: dict[
        str,
        list[dict[str, Any]],
    ],
    target_power: tuple[
        float,
        float,
    ] | None = None,
) -> dict[str, Any]:
    power = _values_for_range(
        streams["power"],
        stream_start,
        start_seconds,
        end_seconds,
    )

    heart_rate = _values_for_range(
        streams["heart_rate"],
        stream_start,
        start_seconds,
        end_seconds,
    )

    cadence = _values_for_range(
        streams["cadence"],
        stream_start,
        start_seconds,
        end_seconds,
    )

    power_first, power_second = (
    _split_half(power)
    )

    hr_first, hr_second = (
        _split_half(heart_rate)
    )

    cadence_first, cadence_second = (
        _split_half(cadence)
    )

    first_half_power = _average(
        power_first
    )
    second_half_power = _average(
        power_second
    )

    first_half_hr = _average(
        hr_first
    )
    second_half_hr = _average(
        hr_second
    )

    power_change_watts = (
        round(
            second_half_power
            - first_half_power,
            1,
        )
        if (
            first_half_power is not None
            and second_half_power is not None
        )
        else None
    )
    power_change_percent = (
        round(
            power_change_watts
            / first_half_power
            * 100,
            1,
        )
        if (
            power_change_watts is not None
            and first_half_power is not None
            and first_half_power > 0
        )
        else None
    )

    heart_rate_drift_bpm = (
        round(
            second_half_hr
            - first_half_hr,
            1,
        )
        if (
            first_half_hr is not None
            and second_half_hr is not None
        )
        else None
    )

    heart_rate_drift_percent = (
        round(
            heart_rate_drift_bpm
            / first_half_hr
            * 100,
            1,
        )
        if (
            heart_rate_drift_bpm is not None
            and first_half_hr is not None
            and first_half_hr > 0
        )
        else None
    )

    is_work_phase = (
    name == "work"
    or name.startswith("work_")
)

    heart_rate_drift_interpretable = (
        is_work_phase
        and end_seconds - start_seconds >= 600
        and first_half_power is not None
        and second_half_power is not None
        and first_half_hr is not None
        and second_half_hr is not None
        and power_change_percent is not None
        and abs(power_change_percent) <= 5.0
    )

    result: dict[str, Any] = {
        "name": name,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds":
            end_seconds - start_seconds,
        "average_power":
            _average(power),
        "average_hr":
            _average(heart_rate),
        "max_hr": (
            round(max(heart_rate), 1)
            if heart_rate
            else None
        ),
        "average_spm":
            _average(cadence),
        "first_half_average_power":
            first_half_power,
        "second_half_average_power":
            second_half_power,

        "first_half_average_hr":
            first_half_hr,
        "second_half_average_hr":
            second_half_hr,

        "power_change_watts":
    power_change_watts,
"power_change_percent":
    power_change_percent,
"power_trend":
    _power_trend(
        power_change_percent
    ),
"heart_rate_drift_bpm":
    heart_rate_drift_bpm,
"heart_rate_drift_percent":
    heart_rate_drift_percent,
"heart_rate_trend":
    _heart_rate_trend(
        heart_rate_drift_bpm
    ),
"heart_rate_drift_interpretable":
    heart_rate_drift_interpretable,
    "first_half_average_spm":
        _average(cadence_first),
    "second_half_average_spm":
        _average(cadence_second),
    "power_stddev": (
        round(pstdev(power), 1)
        if len(power) > 1
        else None
    ),
    }

    if target_power is not None:
        low, high = target_power

        in_target = [
            value
            for value in power
            if low <= value <= high
        ]

        result["target_power_min"] = low
        result["target_power_max"] = high

        result["power_in_target_percent"] = (
            round(
                len(in_target)
                / len(power)
                * 100,
                1,
            )
            if power
            else None
        )

    return result


def analyze_simple_workout_phases(
    *,
    warmup: str | None,
    work: str,
    cooldown: str | None,
    streams: dict[
        str,
        list[dict[str, Any]],
    ],
) -> dict[str, Any]:
    available_streams = [
        points
        for points in streams.values()
        if points
    ]

    if not available_streams:
        raise RuntimeError(
            "No activity streams available"
        )

    stream_start = min(
        points[0]["time"]
        for points in available_streams
    )

    warmup_seconds = _phase_duration(
        warmup
    )
    work_seconds = _phase_duration(
        work
    )
    cooldown_seconds = _phase_duration(
        cooldown
    )

    phases = []

    cursor = 0

    if warmup_seconds:
        phases.append(
            _phase_metrics(
                name="warmup",
                start_seconds=cursor,
                end_seconds=(
                    cursor + warmup_seconds
                ),
                stream_start=stream_start,
                streams=streams,
            )
        )

        cursor += warmup_seconds

    phases.append(
        _phase_metrics(
            name="work",
            start_seconds=cursor,
            end_seconds=(
                cursor + work_seconds
            ),
            stream_start=stream_start,
            streams=streams,
            target_power=_target_power(
                work
            ),
        )
    )

    cursor += work_seconds

    if cooldown_seconds:
        phases.append(
            _phase_metrics(
                name="cooldown",
                start_seconds=cursor,
                end_seconds=(
                    cursor + cooldown_seconds
                ),
                stream_start=stream_start,
                streams=streams,
            )
        )

        cursor += cooldown_seconds

    return {
        "planned_duration_seconds":
            cursor,
        "phases":
            phases,
    }

def _analyze_interval_recovery(
    *,
    stream_start: datetime,
    streams: dict[
        str,
        list[dict[str, Any]],
    ],
    warmup_seconds: int,
    repeat: int,
    work_seconds: int,
    recovery_seconds: int,
) -> list[dict[str, Any]]:
    if (
        repeat <= 1
        or work_seconds <= 0
        or recovery_seconds <= 0
    ):
        return []

    heart_rate = streams.get(
        "heart_rate",
        [],
    )

    if not heart_rate:
        return []

    results = []

    cursor = warmup_seconds

    for repetition in range(
        1,
        repeat + 1,
    ):
        work_start = cursor
        work_end = (
            work_start + work_seconds
        )

        recovery_start = work_end
        recovery_end = (
            recovery_start
            + recovery_seconds
        )

        work_window = min(
            30,
            work_seconds,
        )

        recovery_window = min(
            30,
            recovery_seconds,
        )

        work_end_hr = _average_for_range(
            heart_rate,
            stream_start,
            work_end - work_window,
            work_end,
        )

        early_recovery_values = (
            _values_for_range(
                heart_rate,
                stream_start,
                recovery_start,
                recovery_start
                + recovery_window,
            )
        )

        recovery_peak_hr = (
            _max_rolling_average(
                early_recovery_values,
                window_size=5,
            )
        )

        recovery_end_hr = (
            _average_for_range(
                heart_rate,
                stream_start,
                recovery_end
                - recovery_window,
                recovery_end,
            )
        )

        recovery_bpm = (
            round(
                recovery_peak_hr
                - recovery_end_hr,
                1,
            )
            if (
                recovery_peak_hr
                is not None
                and recovery_end_hr
                is not None
            )
            else None
        )

        results.append(
            {
                "repetition":
                    repetition,
                "work_phase":
                    f"work_{repetition}",
                "recovery_phase":
                    f"recovery_{repetition}",
                "heart_rate_work_end":
                    work_end_hr,
                "heart_rate_recovery_peak":
                    recovery_peak_hr,
                "heart_rate_recovery_end":
                    recovery_end_hr,
                "heart_rate_recovery_bpm":
                    recovery_bpm,
            }
        )

        cursor = recovery_end

    return results

def analyze_workout_phases(
    *,
    warmup: str | None,
    repeat: int,
    work: str,
    recovery: str | None,
    cooldown: str | None,
    streams: dict[
        str,
        list[dict[str, Any]],
    ],
) -> dict[str, Any]:
    available_streams = [
        points
        for points in streams.values()
        if points
    ]

    if not available_streams:
        raise RuntimeError(
            "No activity streams available"
        )

    if repeat < 1:
        raise ValueError(
            "repeat must be at least 1"
        )

    stream_start = min(
        points[0]["time"]
        for points in available_streams
    )

    warmup_seconds = _phase_duration(
        warmup
    )
    work_seconds = _phase_duration(
        work
    )
    recovery_seconds = _phase_duration(
        recovery
    )
    cooldown_seconds = _phase_duration(
        cooldown
    )

    phases = []
    cursor = 0

    if warmup_seconds:
        phases.append(
            _phase_metrics(
                name="warmup",
                start_seconds=cursor,
                end_seconds=(
                    cursor + warmup_seconds
                ),
                stream_start=stream_start,
                streams=streams,
            )
        )

        cursor += warmup_seconds

    for repetition in range(
        1,
        repeat + 1,
    ):
        phases.append(
            _phase_metrics(
                name=f"work_{repetition}",
                start_seconds=cursor,
                end_seconds=(
                    cursor + work_seconds
                ),
                stream_start=stream_start,
                streams=streams,
                target_power=_target_power(
                    work
                ),
            )
        )

        cursor += work_seconds

        # Nach dem letzten Arbeitsintervall keine
        # Recovery mehr einfügen.
        if recovery_seconds:
            phases.append(
                _phase_metrics(
                    name=(
                        f"recovery_{repetition}"
                    ),
                    start_seconds=cursor,
                    end_seconds=(
                        cursor
                        + recovery_seconds
                    ),
                    stream_start=stream_start,
                    streams=streams,
                    target_power=_target_power(
                        recovery
                    ),
                )
            )

            cursor += recovery_seconds

    if cooldown_seconds:
        phases.append(
            _phase_metrics(
                name="cooldown",
                start_seconds=cursor,
                end_seconds=(
                    cursor + cooldown_seconds
                ),
                stream_start=stream_start,
                streams=streams,
            )
        )

        cursor += cooldown_seconds

    stream_end = max(
        points[-1]["time"]
        for points in available_streams
    )

    actual_stream_seconds = int(
        (
            stream_end
            - stream_start
        ).total_seconds()
    ) + 1

    interval_recovery = (
        _analyze_interval_recovery(
            stream_start=stream_start,
            streams=streams,
            warmup_seconds=warmup_seconds,
            repeat=repeat,
            work_seconds=work_seconds,
            recovery_seconds=recovery_seconds,
        )
    )

    return {
        "planned_duration_seconds":
            cursor,
        "actual_stream_seconds":
            actual_stream_seconds,
        "duration_difference_seconds":
            actual_stream_seconds - cursor,
        "phases":
            phases,
        "interval_recovery":
            interval_recovery,
    }