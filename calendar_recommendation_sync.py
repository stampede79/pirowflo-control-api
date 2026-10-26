import json
from datetime import date

from sqlalchemy import select

from calendar_collision_detector import (
    find_calendar_collisions,
)
from database.engine import SessionLocal
from database.models import (
    AvailabilityPeriod,
    CoachRecommendation,
)


def sync_calendar_recommendations(
    *,
    start: date,
    end: date,
) -> dict:
    collisions = find_calendar_collisions(
        start=start,
        end=end,
    )

    created = []
    already_decided = []
    already_pending = []

    with SessionLocal() as session:
        for collision in collisions:
            event_uid = collision.get(
                "event_uid"
            )

            if not event_uid:
                continue

            workout_id = collision[
                "workout_id"
            ]

            # Hat der Benutzer für diesen
            # Kalendereintrag bereits entschieden?
            availability = session.scalar(
                select(AvailabilityPeriod)
                .where(
                    AvailabilityPeriod.external_uid
                    == event_uid
                )
            )

            if availability is not None:
                already_decided.append(
                    {
                        "workout_id": workout_id,
                        "event_uid": event_uid,
                        "status":
                            availability.status,
                    }
                )
                continue

            # Existiert bereits eine offene Frage
            # für genau Workout + Kalenderereignis?
            recommendations = session.scalars(
                select(CoachRecommendation)
                .where(
                    CoachRecommendation.type
                    == "availability_conflict",
                    CoachRecommendation.status
                    == "pending",
                    CoachRecommendation.workout_id
                    == workout_id,
                )
            ).all()

            duplicate = False

            for recommendation in recommendations:
                try:
                    payload = json.loads(
                        recommendation.payload_json
                    )
                except json.JSONDecodeError:
                    continue

                if (
                    payload.get("event_uid")
                    == event_uid
                ):
                    duplicate = True
                    break

            if duplicate:
                already_pending.append(
                    {
                        "workout_id": workout_id,
                        "event_uid": event_uid,
                    }
                )
                continue

            payload = {
                "workout_date":
                    collision[
                        "workout_date"
                    ].isoformat(),
                "workout_name":
                    collision[
                        "workout_name"
                    ],
                "event_uid":
                    event_uid,
                "event_summary":
                    collision[
                        "event_summary"
                    ],
                "event_all_day":
                    collision[
                        "event_all_day"
                    ],
                "event_start":
                    collision[
                        "event_start"
                    ].isoformat(),
                "event_end": (
                    collision[
                        "event_end"
                    ].isoformat()
                    if collision[
                        "event_end"
                    ] is not None
                    else None
                ),
            }

            recommendation = (
                CoachRecommendation(
                    type="availability_conflict",
                    status="pending",
                    action="confirm_availability",
                    workout_id=workout_id,
                    reason=(
                        "Am Trainingstag gibt es "
                        "einen persönlichen "
                        "Kalendereintrag."
                    ),
                    payload_json=json.dumps(
                        payload,
                        ensure_ascii=False,
                    ),
                )
            )

            session.add(recommendation)
            session.flush()

            created.append(
                {
                    "recommendation_id":
                        recommendation.id,
                    "workout_id":
                        workout_id,
                    "event_uid":
                        event_uid,
                    "event_summary":
                        collision[
                            "event_summary"
                        ],
                }
            )

        session.commit()

    return {
        "collisions": len(collisions),
        "created": created,
        "already_decided":
            already_decided,
        "already_pending":
            already_pending,
    }