from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    Workout,
    WorkoutActivityLink,
)
from database.repositories.activity_repository import (
    ActivityRepository,
)
from datetime import date

def link_workout_to_activity(
    workout_id: int,
    endurain_activity_id: int,
) -> dict:
    with SessionLocal() as session:
        workout = session.get(
            Workout,
            workout_id,
        )

        if workout is None:
            raise ValueError(
                "Workout not found"
            )

        activity_repository = (
            ActivityRepository(session)
        )

        activity = (
            activity_repository
            .get_by_endurain_id(
                endurain_activity_id
            )
        )

        if activity is None:
            raise ValueError(
                "Activity not found"
            )

        existing_workout_link = session.scalar(
            select(WorkoutActivityLink)
            .where(
                WorkoutActivityLink.workout_id
                == workout.id
            )
        )

        if existing_workout_link is not None:
            raise ValueError(
                "Workout already linked"
            )

        existing_activity_link = session.scalar(
            select(WorkoutActivityLink)
            .where(
                WorkoutActivityLink.activity_id
                == activity.id
            )
        )

        if existing_activity_link is not None:
            raise ValueError(
                "Activity already linked"
            )

        link = WorkoutActivityLink(
            workout_id=workout.id,
            activity_id=activity.id,
            status="confirmed",
            match_score=1.0,
        )

        session.add(link)

        workout.status = "completed"

        session.commit()

        return {
            "workout_id":
                workout.id,
            "endurain_activity_id":
                activity.endurain_activity_id,
            "status":
                "confirmed",
        }

def link_open_workouts() -> dict:
    created = []
    ambiguous = []
    unmatched = []

    with SessionLocal() as session:
        activity_repository = (
            ActivityRepository(session)
        )

        workouts = session.scalars(
            select(Workout)
            .where(
                Workout.status == "planned",
                Workout.scheduled_date <= date.today(),
            )
            .order_by(
                Workout.scheduled_date
            )
        ).all()

        already_linked_activity_ids = set(
            session.scalars(
                select(
                    WorkoutActivityLink.activity_id
                )
            ).all()
        )

        for workout in workouts:
            existing_link = session.scalar(
                select(WorkoutActivityLink)
                .where(
                    WorkoutActivityLink.workout_id
                    == workout.id
                )
            )

            if existing_link is not None:
                continue

            activities = (
                activity_repository.get_for_date(
                    workout.scheduled_date
                )
            )

            candidates = [
                activity
                for activity in activities
                if activity.id
                not in already_linked_activity_ids
            ]

            if not candidates:
                unmatched.append(
                    {
                        "workout_id": workout.id,
                        "date":
                            workout.scheduled_date,
                        "name": workout.name,
                    }
                )
                continue

            if len(candidates) > 1:
                ambiguous.append(
                    {
                        "workout_id": workout.id,
                        "date":
                            workout.scheduled_date,
                        "name": workout.name,
                        "activity_ids": [
                            activity.endurain_activity_id
                            for activity
                            in candidates
                        ],
                    }
                )
                continue

            activity = candidates[0]

            link = WorkoutActivityLink(
                workout_id=workout.id,
                activity_id=activity.id,
                status="automatic",
                match_score=1.0,
            )

            session.add(link)

            workout.status = "completed"

            already_linked_activity_ids.add(
                activity.id
            )

            created.append(
                {
                    "workout_id": workout.id,
                    "date":
                        workout.scheduled_date,
                    "endurain_activity_id":
                        activity.endurain_activity_id,
                }
            )

        session.commit()

    return {
        "created": created,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
    }