from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any
from datetime import datetime, timedelta


@dataclass(frozen=True)
class StreamQuality:
    raw_samples: int
    clean_samples: int
    excluded_samples: int
    excluded_percent: float
    quality: str


@dataclass(frozen=True)
class CleanedStream:
    points: list[dict[str, Any]]
    quality: StreamQuality


def _quality_label(
    excluded_percent: float,
) -> str:
    if excluded_percent <= 1:
        return "good"

    if excluded_percent <= 5:
        return "fair"

    return "poor"


def _result(
    raw_points: list[dict[str, Any]],
    clean_points: list[dict[str, Any]],
) -> CleanedStream:
    raw_count = len(raw_points)
    clean_count = len(clean_points)
    excluded = raw_count - clean_count

    excluded_percent = (
        round(
            excluded / raw_count * 100,
            1,
        )
        if raw_count
        else 0.0
    )

    return CleanedStream(
        points=clean_points,
        quality=StreamQuality(
            raw_samples=raw_count,
            clean_samples=clean_count,
            excluded_samples=excluded,
            excluded_percent=excluded_percent,
            quality=_quality_label(
                excluded_percent
            ),
        ),
    )


def _is_isolated_spike(
    previous: float,
    current: float,
    following: float,
    *,
    absolute_deviation: float,
    relative_deviation: float,
) -> bool:
    neighbour_level = median(
        [previous, following]
    )

    if neighbour_level <= 0:
        return False

    deviation = abs(
        current - neighbour_level
    )

    relative = deviation / neighbour_level

    neighbours_close = (
        abs(previous - following)
        <= absolute_deviation * 0.5
    )

    return (
        neighbours_close
        and deviation >= absolute_deviation
        and relative >= relative_deviation
    )


def clean_heart_rate_stream(
    points: list[dict[str, Any]],
) -> CleanedStream:
    if len(points) < 3:
        return _result(points, list(points))

    clean = []

    for index, point in enumerate(points):
        value = float(point["value"])

        # Nur eindeutig technisch/unphysiologisch
        # unbrauchbare Werte entfernen.
        if value <= 0 or value > 250:
            continue

        if 0 < index < len(points) - 1:
            previous = float(
                points[index - 1]["value"]
            )
            following = float(
                points[index + 1]["value"]
            )

            if _is_isolated_spike(
                previous,
                value,
                following,
                absolute_deviation=35,
                relative_deviation=0.20,
            ):
                continue

        clean.append(point)

    return _result(points, clean)


def clean_power_stream(
    points: list[dict[str, Any]],
) -> CleanedStream:
    if len(points) < 3:
        return _result(points, list(points))

    clean = []

    for index, point in enumerate(points):
        value = float(point["value"])

        if value < 0:
            continue

        if 0 < index < len(points) - 1:
            previous = float(
                points[index - 1]["value"]
            )
            following = float(
                points[index + 1]["value"]
            )

            # Einzelner Null-Dropout zwischen zwei
            # klar aktiven Leistungssamples.
            if (
                value == 0
                and previous >= 30
                and following >= 30
            ):
                continue

            if _is_isolated_spike(
                previous,
                value,
                following,
                absolute_deviation=150,
                relative_deviation=0.75,
            ):
                continue

        clean.append(point)

    return _result(points, clean)

def _cadence_start_artifact_indices(
    points: list[dict[str, Any]],
) -> set[int]:
    """
    Erkennt kurze, unrealistisch hohe Cadence-Blöcke
    unmittelbar nach mindestens drei Sekunden Stillstand.

    Typische beobachtete SmartRow-Artefakte:
      0, 0, 0, 46, 46, 46, 46, 46, 46, 21, ...
      0, 0, 0, 48, 48, 48, 48, 20, ...
      0, 0, 0, 36, 36, 36, 36, 19, ...

    Normale Starts wie
      0, 0, 0, 22, 22, 22, 20, ...
    bleiben erhalten.
    """
    excluded: set[int] = set()

    if len(points) < 7:
        return excluded

    index = 3

    while index < len(points):
        current = float(
            points[index]["value"]
        )

        previous_three = [
            float(points[i]["value"])
            for i in range(
                index - 3,
                index,
            )
        ]

        # Nur unmittelbar nach mindestens
        # drei 0-SPM-Samples untersuchen.
        if (
            current < 30
            or any(
                value != 0
                for value in previous_three
            )
        ):
            index += 1
            continue

        start = index
        start_level = current

        # SmartRow hält solche Startwerte häufig
        # für mehrere Sekunden konstant.
        while (
            index < len(points)
            and index - start < 8
        ):
            value = float(
                points[index]["value"]
            )

            # Zum auffälligen Startblock zählen Werte,
            # die ungefähr auf dessen hohem Niveau
            # verbleiben.
            if value < start_level * 0.80:
                break

            index += 1

        end = index

        if end >= len(points):
            break

        burst_length = end - start

        # Wir behandeln nur kurze Startartefakte.
        if burst_length > 8:
            continue

        following = [
            float(point["value"])
            for point in points[
                end:min(
                    end + 5,
                    len(points),
                )
            ]
            if float(point["value"]) > 0
        ]

        if len(following) < 3:
            continue

        following_level = median(
            following
        )

        # Der auffällige Startwert muss deutlich
        # oberhalb des danach stabilen Ruderniveaus
        # liegen.
        if (
            following_level < 25
            and start_level
            >= following_level * 1.5
        ):
            excluded.update(
                range(start, end)
            )

    return excluded

def clean_cadence_stream(
    points: list[dict[str, Any]],
) -> CleanedStream:

    if len(points) < 3:
        return _result(
            points,
            list(points),
        )

    start_artifacts = (
        _cadence_start_artifact_indices(
            points
        )
    )

    clean = []

    for index, point in enumerate(points):
        if index in start_artifacts:
            continue

        value = float(point["value"])

        if value < 0:
            continue

        if 0 < index < len(points) - 1:
            previous = float(
                points[index - 1]["value"]
            )
            following = float(
                points[index + 1]["value"]
            )

            if (
                value == 0
                and previous >= 10
                and following >= 10
            ):
                continue

            if _is_isolated_spike(
                previous,
                value,
                following,
                absolute_deviation=20,
                relative_deviation=0.75,
            ):
                continue

        clean.append(point)

    return _result(
        points,
        clean,
    )

@dataclass(frozen=True)
class CleanedActivityStreams:
    streams: dict[str, list[dict[str, Any]]]
    quality: dict[str, StreamQuality]

def _coupled_start_artifact_times(
    cadence_points: list[dict[str, Any]],
    power_points: list[dict[str, Any]],
) -> set[datetime]:
    cadence_indices = (
        _cadence_start_artifact_indices(
            cadence_points
        )
    )

    if not cadence_indices or not power_points:
        return set()

    power_by_time = {
        point["time"]: float(point["value"])
        for point in power_points
    }

    cadence_times = [
        cadence_points[index]["time"]
        for index in sorted(cadence_indices)
    ]

    candidate_values = [
        power_by_time[time]
        for time in cadence_times
        if time in power_by_time
    ]

    if not candidate_values:
        return set()

    last_time = cadence_times[-1]

    following = [
        float(point["value"])
        for point in power_points
        if (
            point["time"] > last_time
            and point["time"]
            <= last_time + timedelta(seconds=5)
            and float(point["value"]) > 0
        )
    ]

    if len(following) < 3:
        return set()

    following_level = median(following)

    if following_level <= 0:
        return set()

    excluded_times = set()

    for time in cadence_times:
        power = power_by_time.get(time)

        if power is None:
            continue

        # Nur deutlich überhöhte Power-Werte innerhalb
        # des bereits bestätigten Cadence-Artefakts.
        if (
            power >= 150
            and power >= following_level * 2.0
        ):
            excluded_times.add(time)

    return excluded_times

def clean_activity_streams(
    
    streams: dict[
        str,
        list[dict[str, Any]],
    ],
) -> CleanedActivityStreams:
    cleaners = {
        "heart_rate": clean_heart_rate_stream,
        "power": clean_power_stream,
        "cadence": clean_cadence_stream,
    }

    coupled_power_artifact_times = (
        _coupled_start_artifact_times(
            streams.get("cadence", []),
            streams.get("power", []),
        )
    )
    cleaned_streams: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    quality: dict[
        str,
        StreamQuality,
    ] = {}

    for name, cleaner in cleaners.items():
        raw_points = streams.get(name, [])

        result = cleaner(raw_points)

        if (
            name == "power"
            and coupled_power_artifact_times
        ):
            coupled_clean_points = [
                point
                for point in result.points
                if point["time"]
                not in coupled_power_artifact_times
            ]

            result = _result(
                raw_points,
                coupled_clean_points,
            )

        cleaned_streams[name] = result.points
        quality[name] = result.quality

    return CleanedActivityStreams(
        streams=cleaned_streams,
        quality=quality,
    )