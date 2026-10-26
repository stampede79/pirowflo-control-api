import json
import os
from datetime import datetime, time

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    AvailabilityPeriod,
    CalendarSync,
    CoachRecommendation,
    Workout,
)
from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)


def _calendar_client() -> NextcloudCalendarClient:
    return NextcloudCalendarClient(
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


def _find_event_by_uid(
    client: NextcloudCalendarClient,
    uid: str,
    around: datetime,
) -> dict:
    start = around.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    # Großes Fenster, weil der gespeicherte Termin
    # noch am ursprünglichen Datum liegen kann.
    from datetime import timedelta

    events = client.get_events_for_range(
        start - timedelta(days=7),
        start + timedelta(days=8),
    )

    for event in events:
        if event.get("uid") == uid:
            return event

    raise RuntimeError(
        f"Calendar event {uid!r} not found"
    )


def apply_replanning_recommendation(
    recommendation_id: int,
) -> dict:
    client = _calendar_client()

    with SessionLocal() as session:
        recommendation = session.get(
            CoachRecommendation,
            recommendation_id,
        )

        if recommendation is None:
            raise RuntimeError(
                "Recommendation not found"
            )

        if recommendation.type != "workout_replanning":
            raise RuntimeError(
                "Recommendation is not a "
                "workout replanning"
            )

        if recommendation.status != "pending":
            raise RuntimeError(
                "Recommendation is not pending"
            )

        payload = json.loads(
            recommendation.payload_json
        )

        workout = session.get(
            Workout,
            recommendation.workout_id,
        )

        if workout is None:
            raise RuntimeError(
                "Workout not found"
            )

        original_date = datetime.fromisoformat(
            payload["original_date"]
        ).date()

        target_date = datetime.fromisoformat(
            payload["target_date"]
        ).date()

        if workout.status != "planned":
            raise RuntimeError(
                "Workout is no longer planned"
            )

        if workout.scheduled_date != original_date:
            raise RuntimeError(
                "Workout date changed since "
                "recommendation was created"
            )

        # Zieltag inzwischen durch anderes Workout
        # belegt?
        occupied = session.scalar(
            select(Workout).where(
                Workout.id != workout.id,
                Workout.scheduled_date
                == target_date,
                Workout.status.in_(
                    ("planned", "completed")
                ),
            )
        )

        if occupied is not None:
            raise RuntimeError(
                "Target date now contains "
                "another workout"
            )

        # Zieltag inzwischen ausdrücklich
        # unavailable?
        unavailable = session.scalar(
            select(AvailabilityPeriod).where(
                AvailabilityPeriod.start_date
                <= target_date,
                AvailabilityPeriod.end_date
                >= target_date,
                AvailabilityPeriod.status
                == "unavailable",
            )
        )

        if unavailable is not None:
            raise RuntimeError(
                "Target date is now unavailable"
            )

        calendar_sync = session.scalar(
            select(CalendarSync).where(
                CalendarSync.workout_id
                == workout.id
            )
        )

        if calendar_sync is None:
            raise RuntimeError(
                "Workout has no CalendarSync"
            )

        calendar_uid = (
            calendar_sync.calendar_uid
        )

        original_datetime = datetime.combine(
            original_date,
            time.min,
        )

        event = _find_event_by_uid(
            client,
            calendar_uid,
            original_datetime,
        )

        # Erst Nextcloud verschieben.
        client.update_event_date(
            event,
            datetime.combine(
                target_date,
                time.min,
            ),
        )

        # Danach den gerade verschobenen Termin
        # erneut laden, damit href/ETag aktuell sind.
        moved_event = _find_event_by_uid(
            client,
            calendar_uid,
            datetime.combine(
                target_date,
                time.min,
            ),
        )

        if (
            moved_event["start"].date()
            != target_date
        ):
            raise RuntimeError(
                "Calendar event did not move "
                "to expected date"
            )

        now = datetime.now()

        try:
            workout.scheduled_date = (
                target_date
            )

            calendar_sync.calendar_href = (
                moved_event.get("href")
            )
            calendar_sync.calendar_etag = (
                moved_event.get("etag")
            )
            calendar_sync.sync_status = (
                "synced"
            )
            calendar_sync.last_synced_at = now

            recommendation.status = "accepted"
            recommendation.accepted_at = now
            recommendation.applied_at = now

            session.commit()

        except Exception:
            session.rollback()

            # Der Nextcloud-Move war zu diesem
            # Zeitpunkt bereits erfolgreich.
            # Nicht behaupten, alles sei
            # zurückgerollt.
            raise RuntimeError(
                "Calendar event was moved, but "
                "SQLite update failed"
            )

        return {
            "recommendation_id":
                recommendation.id,
            "workout_id":
                workout.id,
            "original_date":
                original_date.isoformat(),
            "target_date":
                target_date.isoformat(),
            "calendar_uid":
                calendar_uid,
            "calendar_etag":
                calendar_sync.calendar_etag,
            "status":
                "applied",
        }