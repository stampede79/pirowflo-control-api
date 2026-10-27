import os
from datetime import datetime, timedelta

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    Activity,
    Workout,
    WorkoutActivityLink,
    WorkoutAnalysis,
)
from sync_endurain_activities import sync_activities
from workout_activity_linker import link_open_workouts
from workout_analyzer import (
    MODEL,
    PROMPT_VERSION,
    analyze_endurain_activity,
)
from calendar_recommendation_sync import (
    sync_calendar_recommendations,
)


SYNC_LOOKBACK_DAYS = 14


def _activities_needing_analysis() -> list[int]:
    with SessionLocal() as session:
        rows = session.execute(
            select(
                Activity.endurain_activity_id,
                Workout.id,
            )
            .join(
                WorkoutActivityLink,
                WorkoutActivityLink.activity_id
                == Activity.id,
            )
            .join(
                Workout,
                Workout.id
                == WorkoutActivityLink.workout_id,
            )
            .where(
                Workout.status == "completed"
            )
            .order_by(
                Activity.start_time
            )
        ).all()

        result = []

        for endurain_id, workout_id in rows:
            activity = session.scalar(
                select(Activity).where(
                    Activity.endurain_activity_id
                    == endurain_id
                )
            )

            if activity is None:
                continue

            existing = session.scalar(
                select(WorkoutAnalysis).where(
                    WorkoutAnalysis.workout_id
                    == workout_id,
                    WorkoutAnalysis.activity_id
                    == activity.id,
                    WorkoutAnalysis.model
                    == MODEL,
                    WorkoutAnalysis.prompt_version
                    == PROMPT_VERSION,
                )
            )

            if existing is None:
                result.append(
                    endurain_id
                )

        return result


def run_pipeline() -> dict:
    now = datetime.now()

    openai_calls = 0

    print()
    print("PiRowFlo Coach Pipeline")
    print("=" * 72)
    print(
        "Start:",
        now.isoformat(
            timespec="seconds"
        ),
    )

    print()
    print("1. Endurain synchronisieren")

    sync_result = sync_activities(
        start=now - timedelta(
            days=SYNC_LOOKBACK_DAYS
        ),
        end=now,
    )

    print(
        "   Neu:",
        sync_result["created"],
    )
    print(
        "   Aktualisiert:",
        sync_result["updated"],
    )

    if sync_result["created_activity_ids"]:
        print(
            "   Neue IDs:",
            ", ".join(
                str(value)
                for value
                in sync_result[
                    "created_activity_ids"
                ]
            ),
        )

    print()
    print("2. Workouts zuordnen")

    link_result = link_open_workouts()

    print(
        "   Neue Links:",
        len(link_result["created"]),
    )
    print(
        "   Mehrdeutig:",
        len(link_result["ambiguous"]),
    )
    print(
        "   Ohne Match:",
        len(link_result["unmatched"]),
    )
    print(
        "   Neu als missed:",
        len(link_result["missed"]),
    )

    for item in link_result["missed"]:
        print(
            "   ! Workout #"
            f"{item['workout_id']}"
            " -> missed"
        )

    for item in link_result["created"]:
        print(
            "   + Workout #"
            f"{item['workout_id']}"
            " -> Endurain #"
            f"{item['endurain_activity_id']}"
        )

    print()
    print("3. Fehlende Analysen suchen")

    activity_ids = (
        _activities_needing_analysis()
    )

    print(
        "   Zu analysieren:",
        len(activity_ids),
    )

    analyses = []

    for activity_id in activity_ids:
        print(
            "   Analysiere Endurain #"
            f"{activity_id} ..."
        )

        openai_calls += 1

        analysis = (
            analyze_endurain_activity(
                activity_id
            )
        )

        analyses.append(
            {
                "endurain_activity_id":
                    activity_id,
                "analysis_id":
                    analysis.id,
            }
        )

        print(
            "     -> Analysis #"
            f"{analysis.id}"
        )

        print()
    print("4. Kalenderkonflikte prüfen")

    calendar_start = now.date()

    calendar_end = (
        calendar_start
        + timedelta(days=45)
    )

    calendar_result = (
        sync_calendar_recommendations(
            start=calendar_start,
            end=calendar_end,
        )
    )

    print(
        "   Kollisionen:",
        calendar_result["collisions"],
    )
    print(
        "   Neue Rückfragen:",
        len(
            calendar_result["created"]
        ),
    )
    print(
        "   Bereits entschieden:",
        len(
            calendar_result[
                "already_decided"
            ]
        ),
    )
    print(
        "   Bereits offen:",
        len(
            calendar_result[
                "already_pending"
            ]
        ),
    )

    print()
    print("=" * 72)
    print("Pipeline erfolgreich.")
    print(
        "Neue Activities:",
        sync_result["created"],
    )
    print(
        "Neue Links:",
        len(link_result["created"]),
    )
    print(
        "Neue Analysen:",
        len(analyses),
    )
    print(
        "OpenAI calls:",
        openai_calls,
    )
    print(
        "Neue Kalender-Rückfragen:",
        len(calendar_result["created"]),
    )

    return {
        "sync": sync_result,
        "links": link_result,
        "analyses": analyses,
        "calendar": calendar_result,
        "openai_calls": openai_calls,
    }


def main() -> int:
    try:
        run_pipeline()
        return 0

    except Exception as exc:
        print()
        print("=" * 72)
        print("Pipeline fehlgeschlagen.")
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())