import argparse
import os
from datetime import datetime

from database.engine import SessionLocal
from database.repositories.activity_repository import (
    ActivityRepository,
)
from endurain_client import EndurainClient

def _print_activities(
    start: datetime,
    end: datetime,
    activities: list[dict],
) -> None:
    print()
    print("Endurain Activity Sync")
    print("=" * 72)
    print(
        f"Zeitraum: {start.date()} "
        f"bis {end.date()}"
    )
    print(
        f"Ruderaktivitäten: "
        f"{len(activities)}"
    )
    print()

    for raw in reversed(activities):
        print(
            raw["start_time"],
            "|",
            f"ID {raw['id']}",
            "|",
            f"{raw.get('distance')} m",
            "|",
            f"{raw.get('average_power')} W",
            "|",
            f"HF {raw.get('average_hr')}",
            "|",
            f"SPM {raw.get('average_cad')}",
        )

def sync_activities(
    *,
    start: datetime,
    end: datetime | None = None,
) -> dict:
    if end is None:
        end = datetime.now()

    client = EndurainClient(
        server=os.environ["ENDURAIN_SERVER"],
        username=os.environ[
            "ENDURAIN_USERNAME"
        ],
        password=os.environ[
            "ENDURAIN_PASSWORD"
        ],
    )

    activities = (
        client.get_rowing_activities_for_range(
            start,
            end,
        )
    )

    created = 0
    updated = 0
    created_activity_ids = []

    with SessionLocal() as session:
        try:
            repository = ActivityRepository(
                session
            )

            for raw in activities:
                activity, was_created = (
                    repository.upsert(
                        endurain_activity_id=int(
                            raw["id"]
                        ),
                        start_time=
                            datetime.fromisoformat(
                                raw["start_time"]
                            ),
                        duration_seconds=raw.get(
                            "total_timer_time"
                        ),
                        distance_meters=raw.get(
                            "distance"
                        ),
                        average_power=raw.get(
                            "average_power"
                        ),
                        normalized_power=raw.get(
                            "normalized_power"
                        ),
                        average_hr=raw.get(
                            "average_hr"
                        ),
                        max_hr=raw.get(
                            "max_hr"
                        ),
                        average_spm=raw.get(
                            "average_cad"
                        ),
                    )
                )

                if was_created:
                    created += 1

                    created_activity_ids.append(
                        activity.endurain_activity_id
                    )
                else:
                    updated += 1

            session.commit()

        except Exception:
            session.rollback()
            raise

    return {
        "start": start,
        "end": end,
        "activities": activities,
        "created": created,
        "updated": updated,
        "created_activity_ids":
            created_activity_ids,
    }

def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start",
        default="2026-09-01",
        help="Start date in YYYY-MM-DD",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write activities to SQLite",
    )

    args = parser.parse_args()

    start = datetime.fromisoformat(
        args.start
    )

    end = datetime.now()

    if not args.apply:
        client = EndurainClient(
            server=os.environ[
                "ENDURAIN_SERVER"
            ],
            username=os.environ[
                "ENDURAIN_USERNAME"
            ],
            password=os.environ[
                "ENDURAIN_PASSWORD"
            ],
        )

        activities = (
            client.get_rowing_activities_for_range(
                start,
                end,
            )
        )

        _print_activities(
            start,
            end,
            activities,
        )

        print()
        print(
            "Dry-Run erfolgreich. "
            "SQLite wurde nicht verändert."
        )
        return

    result = sync_activities(
        start=start,
        end=end,
    )

    _print_activities(
        result["start"],
        result["end"],
        result["activities"],
    )

    print()
    print("SQLite aktualisiert.")
    print(
        f"Neu:          "
        f"{result['created']}"
    )
    print(
        f"Aktualisiert: "
        f"{result['updated']}"
    )


if __name__ == "__main__":
    main()