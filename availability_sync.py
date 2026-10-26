import os
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import AvailabilityPeriod
from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)


BLOCK_NAME = "PIROWFLO_AVAILABILITY"


def _parse_availability(
    description: str,
) -> str | None:
    pattern = re.compile(
        rf"\[{BLOCK_NAME}\]"
        r"(.*?)"
        rf"\[/{BLOCK_NAME}\]",
        flags=re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(description)

    if match is None:
        return None

    values = {}

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()

        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)

        values[
            key.strip().lower()
        ] = value.strip().lower()

    status = values.get("status")

    if status not in {
        "unavailable",
        "limited",
    }:
        return None

    return status


def sync_availability(
    *,
    start: date,
    end: date,
) -> dict:
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
        datetime.combine(
            start,
            datetime.min.time(),
        ),
        datetime.combine(
            end,
            datetime.min.time(),
        ),
    )

    now = datetime.now()

    prepared = []

    for event in events:
        if not event["all_day"]:
            continue

        uid = event.get("uid")

        if not uid:
            continue

        status = _parse_availability(
            event["description"]
        )

        if status is None:
            continue

        event_start = event["start"].date()

        raw_end = event.get("end")

        if raw_end is None:
            event_end = event_start
        else:
            # DTEND eines Ganztagstermins ist
            # im iCalendar-Format exklusiv.
            event_end = (
                raw_end.date()
                - timedelta(days=1)
            )

        if event_end < event_start:
            event_end = event_start

        prepared.append(
            {
                "external_uid": uid,
                "start_date": event_start,
                "end_date": event_end,
                "summary": event["summary"],
                "description":
                    event["description"],
                "status": status,
            }
        )

    seen_uids = {
        item["external_uid"]
        for item in prepared
    }

    created = []
    updated = []
    deleted = []

    with SessionLocal() as session:
        existing_periods = session.scalars(
            select(AvailabilityPeriod)
            .where(
                AvailabilityPeriod.source
                == "nextcloud",
                AvailabilityPeriod.start_date
                < end,
                AvailabilityPeriod.end_date
                >= start,
            )
        ).all()

        existing_by_uid = {
            period.external_uid: period
            for period in existing_periods
        }

        for item in prepared:
            period = existing_by_uid.get(
                item["external_uid"]
            )

            if period is None:
                period = AvailabilityPeriod(
                    external_uid=
                        item["external_uid"],
                    start_date=
                        item["start_date"],
                    end_date=
                        item["end_date"],
                    summary=item["summary"],
                    description=
                        item["description"],
                    status=item["status"],
                    source="nextcloud",
                    last_seen_at=now,
                )

                session.add(period)

                created.append(
                    item["external_uid"]
                )

                continue

            changed = any(
                (
                    period.start_date
                    != item["start_date"],
                    period.end_date
                    != item["end_date"],
                    period.summary
                    != item["summary"],
                    period.description
                    != item["description"],
                    period.status
                    != item["status"],
                )
            )

            period.start_date = (
                item["start_date"]
            )
            period.end_date = (
                item["end_date"]
            )
            period.summary = item["summary"]
            period.description = (
                item["description"]
            )
            period.status = item["status"]
            period.last_seen_at = now

            if changed:
                updated.append(
                    item["external_uid"]
                )

        for period in existing_periods:
            if (
                period.external_uid
                in seen_uids
            ):
                continue

            deleted.append(
                period.external_uid
            )

            session.delete(period)

        session.commit()

    return {
        "events_seen": len(events),
        "availability_seen": len(prepared),
        "created": created,
        "updated": updated,
        "deleted": deleted,
    }