from datetime import timedelta
from typing import Any


def build_availability_context(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    unavailable_periods: list[dict[str, str]] = []

    for event in events:
        # V1: Termine mit Uhrzeit beeinflussen die
        # Trainingsplanung nicht automatisch.
        if not event.get("all_day"):
            continue

        start = event.get("start")
        end = event.get("end")

        if start is None or end is None:
            continue

        duration = end.date() - start.date()

        # Eintägige Ganztagstermine wie "Office Erkrath"
        # gelten nicht automatisch als Trainingssperre.
        if duration.days < 2:
            continue

        # DTEND ist bei Ganztagsterminen exklusiv.
        last_unavailable_day = (
            end.date() - timedelta(days=1)
        )

        unavailable_periods.append(
            {
                "start": start.date().isoformat(),
                "end": (
                    last_unavailable_day.isoformat()
                ),
                "reason": event["summary"],
            }
        )

    unavailable_periods.sort(
        key=lambda period: period["start"]
    )

    return {
        "unavailable_periods":
            unavailable_periods,
    }
