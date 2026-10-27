import json
import os
from datetime import date, datetime, timedelta

from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    Activity,
    WeeklyReview,
    Workout,
    WorkoutActivityLink,
    WorkoutAnalysis,
)
import hashlib

MODEL = "gpt-6-luna"
PROMPT_VERSION = "1"


class WeeklyReviewResult(BaseModel):
    assessment: str
    trend: str
    load_assessment: str
    recovery_assessment: str
    consistency: str
    key_observations: list[str]
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

def _week_range(
    year: int,
    iso_week: int,
) -> tuple[date, date]:
    start = date.fromisocalendar(
        year,
        iso_week,
        1,
    )

    end = start + timedelta(days=7)

    return start, end


def build_weekly_review_input(
    year: int,
    iso_week: int,
) -> dict:
    start, end = _week_range(
        year,
        iso_week,
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

        items = []

        total_duration_seconds = 0.0
        total_distance_meters = 0.0

        completed = 0
        skipped = 0
        missed = 0
        planned = 0

        for workout in workouts:
            if workout.status == "completed":
                completed += 1
            elif workout.status == "skipped":
                skipped += 1
            elif workout.status == "missed":
                missed += 1
            elif workout.status == "planned":
                planned += 1

            link = session.scalar(
                select(WorkoutActivityLink)
                .where(
                    WorkoutActivityLink.workout_id
                    == workout.id
                )
                .order_by(
                    WorkoutActivityLink.created_at.desc()
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
                if activity.duration_seconds is not None:
                    total_duration_seconds += (
                        activity.duration_seconds
                    )

                if activity.distance_meters is not None:
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

            items.append(
                {
                    "date":
                        workout.scheduled_date.isoformat(),
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

        return {
            "week": (
                f"{year}-W{iso_week:02d}"
            ),
            "start_date":
                start.isoformat(),
            "end_date":
                (end - timedelta(days=1)).isoformat(),
            "summary_metrics": {
                "planned_workouts":
                    len(workouts),
                "completed_workouts":
                    completed,
                "skipped_workouts":
                    skipped,
                "missed_workouts":
                    missed,
                "open_workouts":
                    planned,
                "total_duration_minutes":
                    round(
                        total_duration_seconds / 60,
                        1,
                    ),
                "total_distance_km":
                    round(
                        total_distance_meters / 1000,
                        2,
                    ),
            },
            "workouts": items,
        }
def generate_weekly_review(
    year: int,
    iso_week: int,
) -> WeeklyReview:
    input_data = build_weekly_review_input(
        year,
        iso_week,
    )

    fingerprint = _input_fingerprint(
        input_data
    )

    with SessionLocal() as session:
        existing = session.scalar(
            select(WeeklyReview)
            .where(
                WeeklyReview.year == year,
                WeeklyReview.iso_week == iso_week,
                WeeklyReview.model == MODEL,
                WeeklyReview.prompt_version
                == PROMPT_VERSION,
                WeeklyReview.input_fingerprint
                == fingerprint,
            )
            .order_by(
                WeeklyReview.created_at.desc()
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

Du bewertest eine komplette Trainingswoche auf Basis
bereits analysierter einzelner Trainingseinheiten.

Die Einzelanalysen wurden aus den tatsächlichen
Endurain-Daten und den geplanten Trainingsvorgaben
erstellt. Verwende sie als primäre Grundlage.

Aufgabe des Wochenreviews ist es, Muster zwischen
mehreren Einheiten zu erkennen. Wiederhole nicht nur
die Einzelanalysen.

Achte insbesondere auf:

- Umsetzung des Trainingsplans
- Verteilung der Belastung
- Leistungsstabilität
- wiederkehrende Auffälligkeiten
- Hinweise auf ausreichende oder eingeschränkte
  Regeneration
- sinnvolle Konsequenzen für die folgende Woche

Wichtig:

Ein recovery_concern in einer einzelnen Einheit ist
ein Beobachtungspunkt und nicht automatisch ein
Regenerationsproblem der gesamten Woche.

Bewerte wiederkehrende Beobachtungen stärker als
einzelne Auffälligkeiten.

Die Durchschnittsleistung einer Gesamtaktivität darf
nicht direkt mit dem Wattziel des Hauptteils
verglichen werden.

Nimm keine Änderungen am Trainingsplan vor.
Empfehlungen sind Hinweise für die weitere
Trainingssteuerung.

Workout-Status:

- completed: Training wurde absolviert.
- planned: Training steht noch aus. Nicht als
  ausgelassen bewerten.
- skipped: Training wurde bewusst ausgelassen
  oder aus dem Plan genommen.
- missed: Der Trainingstermin ist vergangen und
  es wurde keine passende Aktivität gefunden.
  Dies gilt als nicht absolviertes Plantraining.

Berücksichtige missed Workouts bei der Bewertung
der Umsetzung des Trainingsplans. Ein einzelnes
missed Workout rechtfertigt jedoch nicht automatisch
eine grundlegende Änderung des Trainingsplans.

assessment:
- good
- mixed
- concerning
- unknown

trend:
- improving
- stable
- declining
- unclear

load_assessment:
- low
- appropriate
- high
- unknown

recovery_assessment:
- good
- watch
- concerning
- unknown

consistency:
- good
- mixed
- poor
- unknown

key_observations enthält kurze, konkrete
Beobachtungen aus dieser Woche.

summary fasst die Woche kompakt zusammen.

recommendation beschreibt die Konsequenz für die
kommende Trainingswoche.
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
        text_format=WeeklyReviewResult,
    )

    result = response.output_parsed

    if result is None:
        raise RuntimeError(
            "OpenAI returned no weekly review"
        )

    with SessionLocal() as session:
        review = WeeklyReview(
            year=year,
            iso_week=iso_week,
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