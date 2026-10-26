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

def _split_half(
    values: list[float],
) -> tuple[list[float], list[float]]:
    midpoint = len(values) // 2

    return (
        values[:midpoint],
        values[midpoint:],
    )

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
    _average(power_first),
    "second_half_average_power":
        _average(power_second),

    "first_half_average_hr":
        _average(hr_first),
    "second_half_average_hr":
        _average(hr_second),

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
        if (
            recovery_seconds
            and repetition < repeat
        ):
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

    return {
        "planned_duration_seconds":
            cursor,
        "actual_stream_seconds":
            actual_stream_seconds,
        "duration_difference_seconds":
            actual_stream_seconds - cursor,
        "phases":
            phases,
    }