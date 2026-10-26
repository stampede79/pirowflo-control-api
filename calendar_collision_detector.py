import os
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import Workout
from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)


def _event_dates(
    event: dict,
) -> set[date]:
    start = event["start"]

    if event["all_day"]:
        event_start = start.date()

        raw_end = event.get("end")

        if raw_end is None:
            event_end = event_start
        else:
            # iCalendar DTEND ist bei
            # Ganztagsterminen exklusiv.
            event_end = (
                raw_end.date()
                - timedelta(days=1)
            )

        if event_end < event_start:
            event_end = event_start

        result = set()
        current = event_start

        while current <= event_end:
            result.add(current)
            current += timedelta(days=1)

        return result

    return {start.date()}


def find_calendar_collisions(
    *,
    start: date,
    end: date,
) -> list[dict]:
    client = NextcloudCalendarClient(
        calendar_url=os.environ[
            "NEXTCLOUD_AVAILABILITY_CALENDAR_URL"
        ],
        username=os.environ[
            "NEXTCLOUD_USERNAME"
        ],
        app_password=os.environ[
            "NEXTCLOUD_APP_PASSWORD"
        ],
    )

    events = client.get_events_for_range(
        datetime.combine(start, time.min),
        datetime.combine(end, time.min),
    )

    with SessionLocal() as session:
        workouts = session.scalars(
            select(Workout)
            .where(
                Workout.status == "planned",
                Workout.scheduled_date >= start,
                Workout.scheduled_date < end,
            )
            .order_by(
                Workout.scheduled_date
            )
        ).all()

        collisions = []

        for workout in workouts:
            for event in events:
                # Eigene PiRowFlo-Termine aus einem
                # eventuell gemischten Kalender niemals
                # als Konflikt interpretieren.
                description = (
                    event.get("description") or ""
                )

                if "[PIROWFLO]" in description:
                    continue

                if (
                    workout.scheduled_date
                    not in _event_dates(event)
                ):
                    continue

                collisions.append(
                    {
                        "workout_id":
                            workout.id,
                        "workout_date":
                            workout.scheduled_date,
                        "workout_name":
                            workout.name,
                        "event_uid":
                            event.get("uid"),
                        "event_summary":
                            event["summary"],
                        "event_start":
                            event["start"],
                        "event_end":
                            event.get("end"),
                        "event_all_day":
                            event["all_day"],
                    }
                )

        return collisions