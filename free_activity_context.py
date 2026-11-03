from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    Activity,
    WorkoutActivityLink,
)


def get_free_activities(
    session: Session,
    start: date,
    end: date,
) -> list[Activity]:
    start_datetime = datetime.combine(
        start,
        time.min,
    )

    end_datetime = datetime.combine(
        end,
        time.min,
    )

    linked_activity_ids = select(
        WorkoutActivityLink.activity_id
    )

    return list(
        session.scalars(
            select(Activity)
            .where(
                Activity.start_time
                >= start_datetime,
                Activity.start_time
                < end_datetime,
                Activity.id.not_in(
                    linked_activity_ids
                ),
            )
            .order_by(
                Activity.start_time
            )
        ).all()
    )


def serialize_free_activity(
    activity: Activity,
) -> dict:
    return {
        "date":
            activity.start_time.date().isoformat(),
        "start_time":
            activity.start_time.isoformat(),
        "endurain_activity_id":
            activity.endurain_activity_id,
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
    }