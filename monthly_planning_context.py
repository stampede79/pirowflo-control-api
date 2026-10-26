import json
import os
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    Activity,
    AvailabilityPeriod,
    MonthlyReview,
    WeeklyReview,
    Workout,
    WorkoutActivityLink,
    WorkoutAnalysis,
)
from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)


def _month_range(
    year: int,
    month: int,
) -> tuple[date, date]:
    start = date(year, month, 1)

    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    return start, end


def _previous_month(
    year: int,
    month: int,
) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12

    return year, month - 1

def _date_range(
    start: date,
    end_inclusive: date,
) -> list[date]:
    result = []
    current = start

    while current <= end_inclusive:
        result.append(current)
        current += timedelta(days=1)

    return result

def build_monthly_planning_input(
    *,
    target_year: int,
    target_month: int,
) -> dict:
    target_start, target_end = _month_range(
        target_year,
        target_month,
    )

    source_year, source_month = (
        _previous_month(
            target_year,
            target_month,
        )
    )

    source_start, source_end = _month_range(
        source_year,
        source_month,
    )

    with SessionLocal() as session:
        source_workouts = session.scalars(
            select(Workout)
            .where(
                Workout.scheduled_date
                >= source_start,
                Workout.scheduled_date
                < source_end,
            )
            .order_by(
                Workout.scheduled_date
            )
        ).all()

        workout_items = []

        for workout in source_workouts:
            link = session.scalar(
                select(WorkoutActivityLink)
                .where(
                    WorkoutActivityLink.workout_id
                    == workout.id
                )
            )

            activity = None
            analysis = None

            if link is not None:
                activity = session.get(
                    Activity,
                    link.activity_id,
                )

            if activity is not None:
                analysis = session.scalar(
                    select(WorkoutAnalysis)
                    .where(
                        WorkoutAnalysis.workout_id
                        == workout.id,
                        WorkoutAnalysis.activity_id
                        == activity.id,
                    )
                    .order_by(
                        WorkoutAnalysis.created_at.desc()
                    )
                )

            workout_items.append(
                {
                    "date":
                        workout.scheduled_date
                        .isoformat(),
                    "name":
                        workout.name,
                    "status":
                        workout.status,
                    "planned": {
                        "warmup":
                            workout.warmup,
                        "repeat":
                            workout.repeat,
                        "work":
                            workout.work,
                        "recovery":
                            workout.recovery,
                        "cooldown":
                            workout.cooldown,
                    },
                    "actual": (
                        {
                            "duration_minutes": (
                                round(
                                    activity.duration_seconds
                                    / 60,
                                    1,
                                )
                                if activity.duration_seconds
                                is not None
                                else None
                            ),
                            "distance_km": (
                                round(
                                    activity.distance_meters
                                    / 1000,
                                    2,
                                )
                                if activity.distance_meters
                                is not None
                                else None
                            ),
                            "average_power":
                                activity.average_power,
                            "normalized_power":
                                activity.normalized_power,
                            "average_hr":
                                activity.average_hr,
                            "max_hr":
                                activity.max_hr,
                            "average_spm":
                                activity.average_spm,
                        }
                        if activity is not None
                        else None
                    ),
                    "analysis": (
                        {
                            "execution":
                                analysis.execution,
                            "load_assessment":
                                analysis.load_assessment,
                            "effort":
                                analysis.effort,
                            "progression":
                                analysis.progression,
                            "recovery_concern":
                                analysis.recovery_concern,
                            "summary":
                                analysis.summary,
                            "recommendation":
                                analysis.recommendation,
                        }
                        if analysis is not None
                        else None
                    ),
                }
            )

        weekly_rows = session.scalars(
            select(WeeklyReview)
            .where(
                WeeklyReview.input_fingerprint
                != ""
            )
            .order_by(
                WeeklyReview.year.desc(),
                WeeklyReview.iso_week.desc(),
                WeeklyReview.created_at.desc(),
            )
        ).all()

        # Für den Planner reichen die letzten
        # vier aktuellen Weekly Reviews.
        weekly_reviews = []

        seen_weeks = set()

        for review in weekly_rows:
            key = (
                review.year,
                review.iso_week,
            )

            if key in seen_weeks:
                continue

            seen_weeks.add(key)

            details = json.loads(
                review.review_json
            )

            weekly_reviews.append(
                {
                    "week":
                        f"{review.year}-W"
                        f"{review.iso_week:02d}",
                    "assessment":
                        review.assessment,
                    "trend":
                        review.trend,
                    "load_assessment":
                        review.load_assessment,
                    "recovery_assessment":
                        review.recovery_assessment,
                    "consistency":
                        details.get(
                            "consistency"
                        ),
                    "summary":
                        review.summary,
                    "recommendation":
                        details.get(
                            "recommendation"
                        ),
                }
            )

            if len(weekly_reviews) >= 4:
                break

        monthly_review = session.scalar(
            select(MonthlyReview)
            .where(
                MonthlyReview.year
                == source_year,
                MonthlyReview.month
                == source_month,
                MonthlyReview.input_fingerprint
                != "",
            )
            .order_by(
                MonthlyReview.created_at.desc()
            )
        )

        monthly_data = None

        if monthly_review is not None:
            details = json.loads(
                monthly_review.review_json
            )

            monthly_data = {
                "assessment":
                    monthly_review.assessment,
                "trend":
                    monthly_review.trend,
                "load_assessment":
                    monthly_review.load_assessment,
                "recovery_assessment":
                    monthly_review.recovery_assessment,
                "consistency":
                    details.get("consistency"),
                "progression":
                    details.get("progression"),
                "strengths":
                    details.get(
                        "strengths",
                        [],
                    ),
                "focus_areas":
                    details.get(
                        "focus_areas",
                        [],
                    ),
                "summary":
                    monthly_review.summary,
                "recommendation":
                    details.get(
                        "recommendation"
                    ),
            }

        availability_rows = session.scalars(
            select(AvailabilityPeriod)
            .where(
                AvailabilityPeriod.start_date
                < target_end,
                AvailabilityPeriod.end_date
                >= target_start,
            )
            .order_by(
                AvailabilityPeriod.start_date
            )
        ).all()

        availability = [
            {
                "start_date":
                    item.start_date.isoformat(),
                "end_date":
                    item.end_date.isoformat(),
                "status":
                    item.status,
                "summary":
                    item.summary,
                "source":
                    item.source,
            }
            for item in availability_rows
        ]

    # Persönliche Kalendertermine werden nur
    # als Planungskontext gelesen.
    calendar_client = NextcloudCalendarClient(
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

    personal_events = (
        calendar_client.get_events_for_range(
            datetime.combine(
                target_start,
                time.min,
            ),
            datetime.combine(
                target_end,
                time.min,
            ),
        )
    )

    calendar_context = []

    for event in personal_events:
        event_start = event["start"]

        if not (
            target_start
            <= event_start.date()
            < target_end
        ):
            continue

        event_end = event.get("end")

        calendar_context.append(
            {
                "start_date":
                    event_start.date().isoformat(),
                "end_date_exclusive": (
                    event_end.date().isoformat()
                    if event_end is not None
                    else None
                ),
                "summary":
                    event["summary"],
                "all_day":
                    event["all_day"],
            }
        )

    explicit_status_by_date = {}

    for item in availability:
        start_date = date.fromisoformat(
            item["start_date"]
        )
        end_date = date.fromisoformat(
            item["end_date"]
        )

        for current in _date_range(
            start_date,
            end_date,
        ):
            explicit_status_by_date[
                current
            ] = item["status"]

    unavailable_dates = set()
    available_dates = set()
    limited_dates = set()

    for current, status in (
        explicit_status_by_date.items()
    ):
        if status == "unavailable":
            unavailable_dates.add(current)
        elif status == "available":
            available_dates.add(current)
        elif status == "limited":
            limited_dates.add(current)

    # Mehrtägige Ganztagstermine ohne
    # explizite Benutzerentscheidung werden
    # für die Vorplanung vorsichtshalber
    # blockiert.
    for event in calendar_context:
        if not event["all_day"]:
            continue

        raw_end = event[
            "end_date_exclusive"
        ]

        if raw_end is None:
            continue

        event_start = date.fromisoformat(
            event["start_date"]
        )
        event_end_exclusive = (
            date.fromisoformat(raw_end)
        )

        duration_days = (
            event_end_exclusive
            - event_start
        ).days

        if duration_days <= 1:
            continue

        current = event_start

        while current < event_end_exclusive:
            status = (
                explicit_status_by_date.get(
                    current
                )
            )

            # Explizite Benutzerentscheidung
            # hat immer Vorrang.
            if status is None:
                unavailable_dates.add(
                    current
                )

            current += timedelta(days=1)

    planning_constraints = {
        "unavailable_dates": [
            item.isoformat()
            for item in sorted(
                unavailable_dates
            )
        ],
        "explicitly_available_dates": [
            item.isoformat()
            for item in sorted(
                available_dates
            )
        ],
        "limited_dates": [
            item.isoformat()
            for item in sorted(
                limited_dates
            )
        ],
    }

    return {
        "source_month":
            f"{source_year}-{source_month:02d}",
        "target_month":
            f"{target_year}-{target_month:02d}",
        "source_workouts":
            workout_items,
        "weekly_reviews":
            weekly_reviews,
        "monthly_review":
            monthly_data,
        "availability":
            availability,
        "personal_calendar":
            calendar_context,
        "planning_constraints":
            planning_constraints,
    }