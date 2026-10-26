import os
from datetime import datetime

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import Activity
from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)
from training_context import _parse_block
import argparse
from datetime import date, datetime

from database.models import (
    Activity,
    CalendarSync,
    WorkoutActivityLink,
)
from database.repositories.training_plan_repository import (
    TrainingPlanRepository,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write historical workouts to SQLite",
    )

    args = parser.parse_args()
    start = datetime(2026, 10, 1)
    end = datetime(2026, 11, 1)

    calendar = NextcloudCalendarClient(
        calendar_url=os.environ[
            "NEXTCLOUD_CALENDAR_URL"
        ],
        username=os.environ[
            "NEXTCLOUD_USERNAME"
        ],
        app_password=os.environ[
            "NEXTCLOUD_APP_PASSWORD"
        ],
    )

    events = calendar.get_events_for_range(
        start,
        end,
    )

    with SessionLocal() as session:
        activities = {
            activity.endurain_activity_id:
                activity
            for activity in session.scalars(
                select(Activity)
            ).all()
        }

    prepared = []

    for event in sorted(
        events,
        key=lambda item: item["start"],
    ):
        workout = _parse_block(
            event["description"],
            "PIROWFLO",
        )

        if workout is None:
            continue

        result = _parse_block(
            event["description"],
            "PIROWFLO_RESULT",
        )

        activity_id = None

        if result is not None:
            try:
                activity_id = int(
                    result[
                        "endurain_activity_id"
                    ]
                )
            except (KeyError, ValueError):
                activity_id = None

        activity_exists = (
            activity_id in activities
            if activity_id is not None
            else False
        )

        if (
            activity_id is not None
            and not activity_exists
        ):
            raise RuntimeError(
                "Linked Endurain activity is "
                "missing from SQLite: "
                f"{activity_id}"
            )

        status = (
            "completed"
            if activity_id is not None
            else "planned"
        )

        prepared.append(
            {
                "date":
                    event["start"].date(),
                "name":
                    event["summary"],
                "status":
                    status,
                "workout":
                    workout,
                "endurain_activity_id":
                    activity_id,
                "calendar_uid":
                    event.get("uid"),
            }
        )

    print()
    print("Historical Workout Dry-Run")
    print("=" * 72)
    print("Zeitraum: Oktober 2026")
    print()

    for item in prepared:
        activity = (
            f"Endurain #{item['endurain_activity_id']}"
            if item["endurain_activity_id"]
            is not None
            else "kein Link"
        )

        print(
            item["date"],
            "|",
            f"{item['status']:<9}",
            "|",
            item["name"],
            "|",
            activity,
        )

        print(
            "   ",
            "warmup=",
            item["workout"].get("warmup"),
            "| repeat=",
            item["workout"].get(
                "repeat",
                "1",
            ),
            "| work=",
            item["workout"].get("work"),
        )

    completed = sum(
        1
        for item in prepared
        if item["status"] == "completed"
    )

    unlinked = len(prepared) - completed

    print()
    print("=" * 72)
    print("Workouts:", len(prepared))
    print("completed:", completed)
    print("ohne Link:", unlinked)
    print()
    if not args.apply:
        print(
            "Dry-Run erfolgreich. "
            "SQLite wurde nicht verändert."
        )
        return

    print()
    print("Schreibe Oktoberhistorie nach SQLite ...")

    with SessionLocal() as session:
        try:
            repository = TrainingPlanRepository(
                session
            )

            existing = repository.get_plan(
                2026,
                10,
            )

            if existing is not None:
                raise RuntimeError(
                    "Training plan already exists "
                    "in SQLite for 2026-10"
                )

            plan = repository.create_plan(
                year=2026,
                month=10,
                sessions_per_week=None,
                status="historical",
                source="imported",
            )

            for item in prepared:
                workout_data = item["workout"]

                repeat = int(
                    workout_data.get(
                        "repeat",
                        1,
                    )
                )

                work = workout_data.get("work")

                if not work:
                    raise RuntimeError(
                        "Historical workout has no "
                        f"work definition: {item['date']}"
                    )

                workout = repository.add_workout(
                    plan,
                    scheduled_date=item["date"],
                    name=item["name"],
                    description="",
                    status=item["status"],
                    warmup=workout_data.get(
                        "warmup"
                    ),
                    repeat=repeat,
                    work=work,
                    recovery=workout_data.get(
                        "recovery"
                    ),
                    cooldown=workout_data.get(
                        "cooldown"
                    ),
                )

                calendar_uid = item.get(
                    "calendar_uid"
                )

                if calendar_uid:
                    event = next(
                        (
                            event
                            for event in events
                            if event.get("uid")
                            == calendar_uid
                        ),
                        None,
                    )

                    if event is None:
                        raise RuntimeError(
                            "Calendar event disappeared: "
                            f"{calendar_uid}"
                        )

                    session.add(
                        CalendarSync(
                            workout_id=workout.id,
                            calendar_uid=calendar_uid,
                            calendar_href=event.get(
                                "href"
                            ),
                            calendar_etag=event.get(
                                "etag"
                            ),
                            sync_status="synced",
                            last_synced_at=datetime.now(),
                        )
                    )

                activity_id = item.get(
                    "endurain_activity_id"
                )

                if activity_id is not None:
                    activity = session.scalar(
                        select(Activity).where(
                            Activity.endurain_activity_id
                            == activity_id
                        )
                    )

                    if activity is None:
                        raise RuntimeError(
                            "Endurain activity missing "
                            f"from SQLite: {activity_id}"
                        )

                    session.add(
                        WorkoutActivityLink(
                            workout_id=workout.id,
                            activity_id=activity.id,
                            status="confirmed",
                            match_score=None,
                        )
                    )

            session.commit()

        except Exception:
            session.rollback()
            raise

    print(
        "Oktoberhistorie erfolgreich nach "
        "SQLite geschrieben."
    )


if __name__ == "__main__":
    main()