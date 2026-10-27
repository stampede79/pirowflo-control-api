from typing import Any

from sqlalchemy import select

from database.models import (
    Activity,
    CalendarSync,
    Workout,
    WorkoutActivityLink,
)

def serialize_activity(
    activity: Activity,
    *,
    link_status: str | None = None,
) -> dict[str, Any]:
    return {
        "id":
            activity.id,
        "endurain_activity_id":
            activity.endurain_activity_id,
        "start_time":
            activity.start_time.isoformat(),
        "duration_minutes": (
            round(
                activity.duration_seconds / 60,
                1,
            )
            if activity.duration_seconds
            is not None
            else None
        ),
        "distance_km": (
            round(
                activity.distance_meters / 1000,
                2,
            )
            if activity.distance_meters
            is not None
            else None
        ),
        "average_power":
            activity.average_power,
        "normalized_power":
            activity.normalized_power,
        "average_hr":
            activity.average_hr,
        "max_hr":
            activity.max_hr,
        "average_spm":
            activity.average_spm,
        "link_status":
            link_status,
    }

def serialize_workout(
    session,
    workout: Workout,
) -> dict[str, Any]:
    link = session.scalar(
        select(WorkoutActivityLink)
        .where(
            WorkoutActivityLink.workout_id
            == workout.id
        )
        .order_by(
            WorkoutActivityLink.created_at.desc()
        )
    )

    activity = None

    if link is not None:
        activity = session.get(
            Activity,
            link.activity_id,
        )

    activity_data = None

    if activity is not None:
        activity_data = serialize_activity(
            activity,
            link_status=link.status,
        )
    sync = session.scalar(
        select(CalendarSync)
        .where(
            CalendarSync.workout_id
            == workout.id
        )
    )

    return {
        "id":
            workout.id,
        "training_plan_id":
            workout.training_plan_id,
        "scheduled_date":
            workout.scheduled_date.isoformat(),
        "name":
            workout.name,
        "description":
            workout.description,
        "status":
            workout.status,
        "warmup":
            workout.warmup,
        "repeat":
            workout.repeat,
        "work":
            workout.work,
        "recovery":
            workout.recovery,
        "cooldown":
            workout.cooldown,
        "activity":
            activity_data,
        "calendar_sync": (
            {
                "status":
                    sync.sync_status,
            }
            if sync is not None
            else None
        ),
    }