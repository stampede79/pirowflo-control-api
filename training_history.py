from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
from typing import Any

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    Activity,
    Workout,
    WorkoutActivityLink,
)
from database.repositories.activity_repository import (
    ActivityRepository,
)
from workout_api import (
    serialize_activity,
    serialize_workout,
)

from workout_definition import (
    planned_duration_seconds,
)

def _duration_difference(
    workout: Workout,
    activity: Activity,
) -> float:
    if activity.duration_seconds is None:
        return float("inf")

    planned = planned_duration_seconds(
        workout
    )

    return abs(
        planned
        - activity.duration_seconds
    )


def build_training_history(
    start: date,
    end: date,
) -> dict[str, Any]:
    start_dt = datetime.combine(
        start,
        time.min,
    )

    end_dt = datetime.combine(
        end,
        time.min,
    )

    with SessionLocal() as session:
        workouts = list(
            session.scalars(
                select(Workout)
                .where(
                    Workout.scheduled_date
                    >= start,
                    Workout.scheduled_date
                    < end,
                )
                .order_by(
                    Workout.scheduled_date.desc(),
                    Workout.id.desc(),
                )
            )
        )

        activity_repository = (
            ActivityRepository(session)
        )

        activities = (
            activity_repository.get_for_range(
                start_dt,
                end_dt,
            )
        )

        links = list(
            session.scalars(
                select(WorkoutActivityLink)
                .where(
                    WorkoutActivityLink.workout_id
                    .in_([
                        workout.id
                        for workout in workouts
                    ])
                )
            )
        )

        links_by_workout = {
            link.workout_id: link
            for link in links
        }

        used_activity_ids = {
            link.activity_id
            for link in links
        }

        activities_by_id = {
            activity.id: activity
            for activity in activities
        }

        entries = []

        for workout in workouts:
            link = links_by_workout.get(
                workout.id
            )

            if link is not None:
                activity = (
                    activities_by_id.get(
                        link.activity_id
                    )
                )

                entries.append(
                    {
                        "type": "planned",
                        "match_status": "linked",
                        "workout":
                            serialize_workout(
                                session,
                                workout,
                            ),
                        "activity": (
                            serialize_activity(
                                activity,
                                link_status=
                                    link.status,
                            )
                            if activity
                            is not None
                            else None
                        ),
                    }
                )

                continue

            if workout.status == "missed":
                entries.append(
                    {
                        "type": "planned",
                        "match_status": "missed",
                        "workout": serialize_workout(
                            session,
                            workout,
                        ),
                        "activity": None,
                    }
                )

                continue

            if workout.status == "skipped":
                entries.append(
                    {
                        "type": "planned",
                        "match_status": "skipped",
                        "workout":
                            serialize_workout(
                                session,
                                workout,
                            ),
                        "activity": None,
                    }
                )

                continue

            candidates = [
                activity
                for activity in activities
                if (
                    activity.id
                    not in used_activity_ids
                    and activity.start_time.date()
                    == workout.scheduled_date
                )
            ]

            if candidates:
                candidates.sort(
                    key=lambda activity:
                        _duration_difference(
                            workout,
                            activity,
                        )
                )

                candidate = candidates[0]

                used_activity_ids.add(
                    candidate.id
                )

                entries.append(
                    {
                        "type": "planned",
                        "match_status":
                            "candidate",
                        "workout":
                            serialize_workout(
                                session,
                                workout,
                            ),
                        "activity":
                            serialize_activity(
                                candidate,
                            ),
                    }
                )

                continue

            entries.append(
                {
                    "type": "planned",
                    "match_status": "waiting",
                    "workout":
                        serialize_workout(
                            session,
                            workout,
                        ),
                    "activity": None,
                }
            )

        for activity in activities:
            if activity.id in used_activity_ids:
                continue

            entries.append(
                {
                    "type": "free",
                    "match_status": None,
                    "workout": None,
                    "activity":
                        serialize_activity(
                            activity,
                        ),
                }
            )

        entries.sort(
            key=lambda entry: (
                entry["workout"][
                    "scheduled_date"
                ]
                if entry["workout"]
                is not None
                else entry["activity"][
                    "start_time"
                ][:10]
            ),
            reverse=True,
        )

        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "entries": entries,
        }