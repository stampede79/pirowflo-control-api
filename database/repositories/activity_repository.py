from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Activity
from datetime import date, datetime, time, timedelta


class ActivityRepository:
    def __init__(
        self,
        session: Session,
    ):
        self.session = session

    def get_by_endurain_id(
        self,
        endurain_activity_id: int,
    ) -> Activity | None:
        return self.session.scalar(
            select(Activity).where(
                Activity.endurain_activity_id
                == endurain_activity_id
            )
        )

    def upsert(
        self,
        *,
        endurain_activity_id: int,
        start_time: datetime,
        duration_seconds: float | None,
        distance_meters: float | None,
        average_power: float | None,
        normalized_power: float | None,
        average_hr: float | None,
        max_hr: float | None,
        average_spm: float | None,
    ) -> tuple[Activity, bool]:
        activity = self.get_by_endurain_id(
            endurain_activity_id
        )

        created = activity is None

        if activity is None:
            activity = Activity(
                endurain_activity_id=
                    endurain_activity_id,
                start_time=start_time,
            )

            self.session.add(activity)

        activity.start_time = start_time
        activity.duration_seconds = (
            duration_seconds
        )
        activity.distance_meters = (
            distance_meters
        )
        activity.average_power = average_power
        activity.normalized_power = (
            normalized_power
        )
        activity.average_hr = average_hr
        activity.max_hr = max_hr
        activity.average_spm = average_spm

        self.session.flush()

        return activity, created
    
    def get_for_date(
        self,
        activity_date: date,
    ) -> list[Activity]:
        start = datetime.combine(
            activity_date,
            time.min,
        )

        end = start + timedelta(days=1)

        return self.get_for_range(
            start,
            end,
        )

    def get_for_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[Activity]:
        return list(
            self.session.scalars(
                select(Activity)
                .where(
                    Activity.start_time >= start,
                    Activity.start_time < end,
                )
                .order_by(
                    Activity.start_time
                )
            )
        )