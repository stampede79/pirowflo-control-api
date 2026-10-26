from datetime import date, timedelta

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    AvailabilityPeriod,
    CoachRecommendation,
    Workout,
)
import json




SEARCH_DAYS = 3

def create_replanning_recommendation(
    workout_id: int,
) -> CoachRecommendation | None:
    result = find_replanning_candidates(
        workout_id
    )

    candidates = result["candidates"]

    if len(candidates) != 1:
        return None

    candidate = candidates[0]
    workout_data = result["workout"]

    with SessionLocal() as session:
        existing = session.scalars(
            select(CoachRecommendation)
            .where(
                CoachRecommendation.type
                == "workout_replanning",
                CoachRecommendation.status
                == "pending",
                CoachRecommendation.workout_id
                == workout_id,
            )
        ).all()

        for recommendation in existing:
            try:
                payload = json.loads(
                    recommendation.payload_json
                )
            except json.JSONDecodeError:
                continue

            if (
                payload.get("target_date")
                == candidate["date"]
            ):
                return recommendation

        payload = {
            "original_date":
                workout_data["date"],
            "target_date":
                candidate["date"],
            "workout_name":
                workout_data["name"],
            "offset_days":
                candidate["offset_days"],
            "days_after_previous":
                candidate[
                    "days_after_previous"
                ],
            "days_before_following":
                candidate[
                    "days_before_following"
                ],
            "previous_workout":
                candidate[
                    "previous_workout"
                ],
            "following_workout":
                candidate[
                    "following_workout"
                ],
        }

        recommendation = CoachRecommendation(
            type="workout_replanning",
            status="pending",
            action="reschedule_workout",
            workout_id=workout_id,
            reason=(
                "Das geplante Training kollidiert "
                "mit deiner bestätigten "
                "Nichtverfügbarkeit. Es gibt einen "
                "geeigneten alternativen "
                "Trainingstag."
            ),
            payload_json=json.dumps(
                payload,
                ensure_ascii=False,
            ),
        )

        session.add(recommendation)
        session.commit()
        session.refresh(recommendation)

        return recommendation
        
def find_replanning_candidates(
    workout_id: int,
) -> dict:
    with SessionLocal() as session:
        workout = session.get(
            Workout,
            workout_id,
        )

        if workout is None:
            raise RuntimeError(
                f"Workout #{workout_id} not found"
            )

        original_date = workout.scheduled_date

        candidates = []

        for offset in range(
            -SEARCH_DAYS,
            SEARCH_DAYS + 1,
        ):
            if offset == 0:
                continue

            candidate_date = (
                original_date
                + timedelta(days=offset)
            )

            # Nicht in die Vergangenheit.
            if candidate_date < date.today():
                continue

            # Bereits anderes Workout an diesem Tag?
            other_workout = session.scalar(
                select(Workout)
                .where(
                    Workout.id != workout.id,
                    Workout.scheduled_date
                    == candidate_date,
                    Workout.status.in_(
                        (
                            "planned",
                            "completed",
                        )
                    ),
                )
            )

            if other_workout is not None:
                continue

            # Benutzer hat den Tag ausdrücklich
            # als unavailable markiert?
            unavailable = session.scalar(
                select(AvailabilityPeriod)
                .where(
                    AvailabilityPeriod.start_date
                    <= candidate_date,
                    AvailabilityPeriod.end_date
                    >= candidate_date,
                    AvailabilityPeriod.status
                    == "unavailable",
                )
            )

            if unavailable is not None:
                continue

            # Abstand zu den umliegenden Workouts.
            previous = session.scalar(
                select(Workout)
                .where(
                    Workout.id != workout.id,
                    Workout.scheduled_date
                    < candidate_date,
                    Workout.status.in_(
                        (
                            "planned",
                            "completed",
                        )
                    ),
                )
                .order_by(
                    Workout.scheduled_date.desc()
                )
            )

            following = session.scalar(
                select(Workout)
                .where(
                    Workout.id != workout.id,
                    Workout.scheduled_date
                    > candidate_date,
                    Workout.status.in_(
                        (
                            "planned",
                            "completed",
                        )
                    ),
                )
                .order_by(
                    Workout.scheduled_date
                )
            )

            days_after_previous = (
                (
                    candidate_date
                    - previous.scheduled_date
                ).days
                if previous is not None
                else None
            )

            days_before_following = (
                (
                    following.scheduled_date
                    - candidate_date
                ).days
                if following is not None
                else None
            )

                        # Wenn möglich keine Einheiten an
            # direkt aufeinanderfolgenden Tagen.
            if (
                days_after_previous is not None
                and days_after_previous < 2
            ):
                continue

            if (
                days_before_following is not None
                and days_before_following < 2
            ):
                continue

            candidates.append(
                {
                    "date":
                        candidate_date.isoformat(),
                    "offset_days":
                        offset,
                    "days_after_previous":
                        days_after_previous,
                    "previous_workout": (
                        {
                            "date":
                                previous
                                .scheduled_date
                                .isoformat(),
                            "name":
                                previous.name,
                        }
                        if previous is not None
                        else None
                    ),
                    "days_before_following":
                        days_before_following,
                    "following_workout": (
                        {
                            "date":
                                following
                                .scheduled_date
                                .isoformat(),
                            "name":
                                following.name,
                        }
                        if following is not None
                        else None
                    ),
                }
            )

        return {
            "workout": {
                "id": workout.id,
                "date":
                    original_date.isoformat(),
                "name": workout.name,
                "warmup": workout.warmup,
                "repeat": workout.repeat,
                "work": workout.work,
                "recovery": workout.recovery,
                "cooldown": workout.cooldown,
            },
            "candidates": candidates,
        }