import re
from datetime import datetime
from typing import Any


def _parse_block(
    description: str,
    name: str,
) -> dict[str, str] | None:
    match = re.search(
        rf"\[{re.escape(name)}\](.*?)\[/{re.escape(name)}\]",
        description,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match is None:
        return None

    values: dict[str, str] = {}

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()

        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)

        values[key.strip().lower()] = value.strip()

    return values


def _actual_activity(
    activity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "endurain_activity_id": int(activity["id"]),
        "date": activity["start_time"][:10],
        "duration_minutes": round(
            activity.get("total_timer_time", 0) / 60,
            1,
        ),
        "distance_km": round(
            activity.get("distance", 0) / 1000,
            2,
        ),
        "average_power": activity.get("average_power"),
        "average_hr": activity.get("average_hr"),
        "max_hr": activity.get("max_hr"),
        "average_spm": activity.get("average_cad"),
        "normalized_power": activity.get(
            "normalized_power"
        ),
    }


def build_training_context(
    events: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    activities_by_id = {
        int(activity["id"]): activity
        for activity in activities
    }

    linked_activity_ids: set[int] = set()
    planned_workouts: list[dict[str, Any]] = []

    for event in events:
        workout = _parse_block(
            event["description"],
            "PIROWFLO",
        )

        # Nur strukturierte PiRowFlo-Trainings gelten als
        # geplante Trainings.
        if workout is None:
            continue

        result = _parse_block(
            event["description"],
            "PIROWFLO_RESULT",
        )

        activity_id = None
        actual = None

        if result is not None:
            try:
                activity_id = int(
                    result["endurain_activity_id"]
                )
            except (KeyError, ValueError):
                activity_id = None

        if activity_id is not None:
            linked_activity_ids.add(activity_id)

            activity = activities_by_id.get(activity_id)

            if activity is not None:
                actual = _actual_activity(activity)

        event_date = event["start"].date()

        if event_date > now.date():
            status = "future"
        elif actual is not None:
            status = "linked"
        else:
            status = "unlinked"

        planned_workouts.append(
            {
                "date": event_date.isoformat(),
                "name": event["summary"],
                "status": status,
                "workout": workout,
                "actual": actual,
            }
        )

    free_activities = [
        _actual_activity(activity)
        for activity in activities
        if int(activity["id"])
        not in linked_activity_ids
    ]

    planned_workouts.sort(
        key=lambda item: item["date"]
    )

    free_activities.sort(
        key=lambda item: item["date"]
    )

    return {
        "generated_at": now.isoformat(),
        "planned_workouts": planned_workouts,
        "free_activities": free_activities,
    }
