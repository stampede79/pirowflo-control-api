import json
import os
from datetime import datetime
from pathlib import Path

from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)
import argparse
from datetime import date, datetime

from database.engine import SessionLocal
from database.models import CalendarSync
from database.repositories.training_plan_repository import (
    TrainingPlanRepository,
)


PLAN_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the migration to SQLite",
    )

    args = parser.parse_args()
    target_month = "2026-11"

    plan_file = (
        PLAN_DIR /
        f"{target_month}.json"
    )

    data = json.loads(
        plan_file.read_text(
            encoding="utf-8",
        )
    )

    if data.get("status") != "applied":
        raise RuntimeError(
            "Training plan is not applied"
        )

    workouts = data.get("workouts")

    if not isinstance(workouts, list):
        raise RuntimeError(
            "Training plan has no workouts"
        )

    year, month = map(
        int,
        target_month.split("-"),
    )

    start = datetime(
        year,
        month,
        1,
    )

    if month == 12:
        end = datetime(
            year + 1,
            1,
            1,
        )
    else:
        end = datetime(
            year,
            month + 1,
            1,
        )

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

    events_by_uid = {
        event["uid"]: event
        for event in events
        if event.get("uid")
    }

    print()
    print(
        f"Migration Dry-Run {target_month}"
    )
    print("=" * 72)

    prepared = []

    for workout in workouts:
        workout_date = workout["date"]

        uid = (
            "pirowflo-plan-"
            f"{target_month}-"
            f"{workout_date}"
            "@pirowflo"
        )

        event = events_by_uid.get(uid)

        if event is None:
            raise RuntimeError(
                "Calendar event not found: "
                f"{uid}"
            )

        description = event["description"]

        status = (
            "skipped"
            if "status=skipped" in description
            else "planned"
        )

        repeat = workout.get(
            "repeat",
            1,
        )

        repeat = int(repeat)

        prepared.append(
            {
                "date": workout_date,
                "name": workout["name"],
                "status": status,
                "warmup": workout.get(
                    "warmup"
                ),
                "repeat": repeat,
                "work": workout["work"],
                "recovery": workout.get(
                    "recovery"
                ),
                "cooldown": workout.get(
                    "cooldown"
                ),
                "calendar_uid": uid,
                "calendar_href":
                    event.get("href"),
                "calendar_etag":
                    event.get("etag"),
            }
        )

    if len(prepared) != len(workouts):
        raise RuntimeError(
            "Prepared workout count mismatch"
        )

    print()
    print("TrainingPlan")
    print(
        f"  month={target_month}"
    )
    print(
        "  status=approved"
    )
    print(
        "  sessions_per_week="
        f"{data['sessions_per_week']}"
    )
    print(
        "  source=ai"
    )

    print()
    print("Workouts")

    for workout in prepared:
        print(
            f"  {workout['date']} | "
            f"{workout['status']:<7} | "
            f"{workout['name']}"
        )

    planned = sum(
        1
        for workout in prepared
        if workout["status"] == "planned"
    )

    skipped = sum(
        1
        for workout in prepared
        if workout["status"] == "skipped"
    )

    print()
    print("CalendarSync")
    print(
        f"  {len(prepared)} mappings"
    )

    print()
    print("=" * 72)
    print(
        f"Workouts: {len(prepared)}"
    )
    print(
        f"planned:  {planned}"
    )
    print(
        f"skipped:  {skipped}"
    )
    print()
    if not args.apply:
        print(
            "Dry-Run erfolgreich. "
            "SQLite wurde nicht verändert."
        )
        return

    print()
    print("Schreibe Daten nach SQLite ...")

    with SessionLocal() as session:
        try:
            repository = TrainingPlanRepository(
                session
            )

            existing = repository.get_plan(
                year,
                month,
            )

            if existing is not None:
                raise RuntimeError(
                    "Training plan already exists "
                    f"in SQLite for {target_month}"
                )

            plan = repository.create_plan(
                year=year,
                month=month,
                sessions_per_week=int(
                    data["sessions_per_week"]
                ),
                status="approved",
                source="ai",
            )

            for item in prepared:
                workout = repository.add_workout(
                    plan,
                    scheduled_date=date.fromisoformat(
                        item["date"]
                    ),
                    name=item["name"],
                    description="",
                    status=item["status"],
                    warmup=item["warmup"],
                    repeat=item["repeat"],
                    work=item["work"],
                    recovery=item["recovery"],
                    cooldown=item["cooldown"],
                )

                sync = CalendarSync(
                    workout_id=workout.id,
                    calendar_uid=item[
                        "calendar_uid"
                    ],
                    calendar_href=item[
                        "calendar_href"
                    ],
                    calendar_etag=item[
                        "calendar_etag"
                    ],
                    sync_status="synced",
                    last_synced_at=datetime.now(),
                )

                session.add(sync)

            session.commit()

        except Exception:
            session.rollback()
            raise

    print(
        "Migration erfolgreich nach SQLite "
        "geschrieben."
    )


if __name__ == "__main__":
    main()