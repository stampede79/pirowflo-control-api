import json

from datetime import date, timedelta

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    Activity,
    MonthlyReview,
    WeeklyReview,
    Workout,
    WorkoutActivityLink,
    WorkoutAnalysis,
)
import hashlib
import os

from openai import OpenAI
from pydantic import BaseModel

MODEL = "gpt-6-luna"
PROMPT_VERSION = "1"


class MonthlyReviewResult(BaseModel):
    assessment: str
    trend: str
    load_assessment: str
    recovery_assessment: str
    consistency: str
    progression: str
    key_observations: list[str]
    strengths: list[str]
    focus_areas: list[str]
    summary: str
    recommendation: str

def _input_fingerprint(
    input_data: dict,
) -> str:
    canonical = json.dumps(
        input_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

def _month_range(
    year: int,
    month: int,
) -> tuple[date, date]:
    start = date(
        year,
        month,
        1,
    )

    if month == 12:
        end = date(
            year + 1,
            1,
            1,
        )
    else:
        end = date(
            year,
            month + 1,
            1,
        )

    return start, end


def _week_keys_for_month(
    start: date,
    end: date,
) -> set[tuple[int, int]]:
    result = set()

    current = start

    while current < end:
        iso = current.isocalendar()

        monday = date.fromisocalendar(
            iso.year,
            iso.week,
            1,
        )

        if (
            monday >= start
            and monday < end
        ):
            result.add(
                (
                    iso.year,
                    iso.week,
                )
            )

        current += timedelta(days=1)

    return result


def build_monthly_review_input(
    year: int,
    month: int,
) -> dict:
    start, end = _month_range(
        year,
        month,
    )

    week_keys = _week_keys_for_month(
        start,
        end,
    )

    with SessionLocal() as session:
        workouts = session.scalars(
            select(Workout)
            .where(
                Workout.scheduled_date >= start,
                Workout.scheduled_date < end,
            )
            .order_by(
                Workout.scheduled_date
            )
        ).all()

        completed = 0
        skipped = 0
        planned = 0

        total_duration_seconds = 0.0
        total_distance_meters = 0.0

        workout_items = []

        for workout in workouts:
            if workout.status == "completed":
                completed += 1
            elif workout.status == "skipped":
                skipped += 1
            elif workout.status == "planned":
                planned += 1

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
                if (
                    activity.duration_seconds
                    is not None
                ):
                    total_duration_seconds += (
                        activity.duration_seconds
                    )

                if (
                    activity.distance_meters
                    is not None
                ):
                    total_distance_meters += (
                        activity.distance_meters
                    )

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
                        workout.scheduled_date.isoformat(),
                    "name":
                        workout.name,
                    "status":
                        workout.status,
                    "actual": (
                        {
                            "endurain_activity_id":
                                activity.endurain_activity_id,
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
                            "prompt_version":
                                analysis.prompt_version,
                        }
                        if analysis is not None
                        else None
                    ),
                }
            )

        weekly_reviews = []

        for week_year, iso_week in sorted(
            week_keys
        ):
            review = session.scalar(
                select(WeeklyReview)
                .where(
                    WeeklyReview.year
                    == week_year,
                    WeeklyReview.iso_week
                    == iso_week,
                    WeeklyReview.input_fingerprint
                    != "",
                )
                .order_by(
                    WeeklyReview.created_at.desc()
                )
            )

            if review is None:
                continue

            details = json.loads(
                review.review_json
            )

            weekly_reviews.append(
                {
                    "week":
                        f"{week_year}-W"
                        f"{iso_week:02d}",
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
                    "key_observations":
                        details.get(
                            "key_observations",
                            [],
                        ),
                    "summary":
                        review.summary,
                    "recommendation":
                        details.get(
                            "recommendation"
                        ),
                }
            )

        return {
            "month":
                f"{year}-{month:02d}",
            "start_date":
                start.isoformat(),
            "end_date":
                (
                    end
                    - timedelta(days=1)
                ).isoformat(),
            "summary_metrics": {
                "planned_workouts":
                    len(workouts),
                "completed_workouts":
                    completed,
                "skipped_workouts":
                    skipped,
                "open_workouts":
                    planned,
                "total_duration_minutes":
                    round(
                        total_duration_seconds
                        / 60,
                        1,
                    ),
                "total_distance_km":
                    round(
                        total_distance_meters
                        / 1000,
                        2,
                    ),
            },
            "weekly_reviews":
                weekly_reviews,
            "workouts":
                workout_items,
        }
    
def generate_monthly_review(
    year: int,
    month: int,
) -> MonthlyReview:
    input_data = build_monthly_review_input(
        year,
        month,
    )

    fingerprint = _input_fingerprint(
        input_data
    )

    with SessionLocal() as session:
        existing = session.scalar(
            select(MonthlyReview)
            .where(
                MonthlyReview.year == year,
                MonthlyReview.month == month,
                MonthlyReview.model == MODEL,
                MonthlyReview.prompt_version
                == PROMPT_VERSION,
                MonthlyReview.input_fingerprint
                == fingerprint,
            )
            .order_by(
                MonthlyReview.created_at.desc()
            )
        )

        if existing is not None:
            return existing

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
    )

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """
Du bist ein Trainingscoach für Indoor-Rudern.

Du bewertest einen vollständigen Trainingsmonat.

Dir stehen deterministische Monatskennzahlen,
bereits erzeugte Wochenreviews und die aktuellen
Analysen der einzelnen Trainingseinheiten zur
Verfügung.

Nutze Wochenreviews, um wiederkehrende Muster zu
erkennen. Nutze Einzelanalysen für konkrete
Beobachtungen. Wiederhole nicht lediglich die
vorhandenen Texte.

Bewerte insbesondere:

- Umsetzung des Trainingsplans
- Trainingskonsistenz
- Belastungsverteilung
- Entwicklung der Leistungsfähigkeit
- wiederkehrende Herzfrequenz- oder
  Regenerationsmuster
- Qualität unterschiedlicher Trainingsformen
- sinnvolle Schwerpunkte für den Folgemonat

Eine einzelne auffällige Einheit ist kein
Monatstrend. Wiederkehrende Beobachtungen über
mehrere Einheiten oder Wochen sind stärker zu
gewichten.

Nimm selbst keine Änderungen an einem bestehenden
Trainingsplan vor.

Die Empfehlung soll eine Grundlage für die
Trainingsplanung des Folgemonats bilden.

assessment:
good, mixed, concerning oder unknown

trend:
improving, stable, declining oder unclear

load_assessment:
low, appropriate, high oder unknown

recovery_assessment:
good, watch, concerning oder unknown

consistency:
good, mixed, poor oder unknown

progression:
positive, stable, concerning oder unclear

strengths enthält kurze konkrete Stärken des Monats.

focus_areas enthält konkrete Trainingsschwerpunkte
für den Folgemonat.

key_observations enthält die wichtigsten
monatsübergreifenden Beobachtungen.

summary fasst den Trainingsmonat kompakt zusammen.

recommendation beschreibt die Konsequenz für die
Trainingssteuerung im Folgemonat.
""",
            },
            {
                "role": "user",
                "content": json.dumps(
                    input_data,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
        text_format=MonthlyReviewResult,
    )

    result = response.output_parsed

    if result is None:
        raise RuntimeError(
            "OpenAI returned no monthly review"
        )

    with SessionLocal() as session:
        review = MonthlyReview(
            year=year,
            month=month,
            assessment=result.assessment,
            trend=result.trend,
            load_assessment=
                result.load_assessment,
            recovery_assessment=
                result.recovery_assessment,
            summary=result.summary,
            review_json=json.dumps(
                result.model_dump(),
                ensure_ascii=False,
            ),
            model=MODEL,
            prompt_version=PROMPT_VERSION,
            input_fingerprint=fingerprint,
        )

        session.add(review)
        session.commit()
        session.refresh(review)

        return review