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
from typing import Literal

from free_activity_context import (
    get_free_activities,
    get_free_activity_analysis,
    serialize_free_activity,
)

MODEL = "gpt-6-luna"
PROMPT_VERSION = "6"


class MonthlyReviewResult(BaseModel):
    assessment: Literal[
        "good",
        "mixed",
        "concerning",
        "unknown",
    ]

    trend: Literal[
        "improving",
        "stable",
        "declining",
        "unclear",
    ]

    load_assessment: Literal[
        "low",
        "appropriate",
        "high",
        "unknown",
    ]

    recovery_assessment: Literal[
        "good",
        "watch",
        "concerning",
        "unknown",
    ]

    consistency: Literal[
        "good",
        "mixed",
        "poor",
        "unknown",
    ]

    progression: Literal[
        "positive",
        "stable",
        "concerning",
        "unclear",
    ]

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

def _power_target_status(
    average_power: float | None,
    target_min: float | None,
    target_max: float | None,
) -> str:
    if (
        average_power is None
        or target_min is None
        or target_max is None
    ):
        return "unknown"

    if average_power < target_min:
        return "below_target"

    if average_power > target_max:
        return "above_target"

    return "in_target"


def _phase_number(
    phase: dict,
    prefix: str,
) -> int:
    name = phase.get("name", "")

    try:
        return int(
            name.removeprefix(prefix)
        )
    except ValueError:
        return 0


def _continuous_work_metrics(
    phases: list[dict],
) -> dict | None:
    work_phases = [
        phase
        for phase in phases
        if phase.get("name", "").startswith("work_")
    ]

    if len(work_phases) != 1:
        return None

    phase = work_phases[0]

    average_power = phase.get("average_power")
    target_min = phase.get("target_power_min")
    target_max = phase.get("target_power_max")

    return {
        "duration_minutes": round(
            phase.get("duration_seconds", 0) / 60,
            1,
        ),
        "average_power":
            average_power,
        "target_power_min":
            target_min,
        "target_power_max":
            target_max,
        "power_target_status":
            _power_target_status(
                average_power,
                target_min,
                target_max,
            ),
        "power_stddev":
            phase.get("power_stddev"),
        "power_trend":
            phase.get("power_trend"),
        "average_hr":
            phase.get("average_hr"),
        "max_hr":
            phase.get("max_hr"),
        "heart_rate_trend":
            phase.get("heart_rate_trend"),
        "heart_rate_drift_bpm":
            phase.get("heart_rate_drift_bpm"),
        "heart_rate_drift_interpretable":
            phase.get(
                "heart_rate_drift_interpretable"
            ),
        "average_spm":
            phase.get("average_spm"),
    }


def _interval_work_metrics(
    phases: list[dict],
    interval_recovery: list[dict],
) -> dict | None:
    work_phases = sorted(
        [
            phase
            for phase in phases
            if phase.get("name", "").startswith(
                "work_"
            )
        ],
        key=lambda phase: _phase_number(
            phase,
            "work_",
        ),
    )

    recovery_phases = sorted(
        [
            phase
            for phase in phases
            if phase.get("name", "").startswith(
                "recovery_"
            )
        ],
        key=lambda phase: _phase_number(
            phase,
            "recovery_",
        ),
    )

    if len(work_phases) <= 1:
        return None

    def status(phase: dict) -> str:
        return _power_target_status(
            phase.get("average_power"),
            phase.get("target_power_min"),
            phase.get("target_power_max"),
        )

    work_statuses = [
        status(phase)
        for phase in work_phases
    ]

    recovery_statuses = [
        status(phase)
        for phase in recovery_phases
    ]

    work_powers = [
        phase.get("average_power")
        for phase in work_phases
        if phase.get("average_power") is not None
    ]

    recovery_powers = [
        phase.get("average_power")
        for phase in recovery_phases
        if phase.get("average_power") is not None
    ]

    hr_recoveries = [
        item.get("heart_rate_recovery_bpm")
        for item in interval_recovery
        if item.get("heart_rate_recovery_bpm")
        is not None
    ]

    return {
        "repetitions":
            len(work_phases),
        "work_phases":
            len(work_phases),
        "work_in_target":
            work_statuses.count("in_target"),
        "work_below_target":
            work_statuses.count("below_target"),
        "work_above_target":
            work_statuses.count("above_target"),
        "average_work_power": (
            round(
                sum(work_powers)
                / len(work_powers),
                1,
            )
            if work_powers
            else None
        ),
        "recovery_phases":
            len(recovery_phases),
        "recovery_in_target":
            recovery_statuses.count("in_target"),
        "recovery_below_target":
            recovery_statuses.count(
                "below_target"
            ),
        "recovery_above_target":
            recovery_statuses.count(
                "above_target"
            ),
        "average_recovery_power": (
            round(
                sum(recovery_powers)
                / len(recovery_powers),
                1,
            )
            if recovery_powers
            else None
        ),
        "average_hr_recovery_bpm": (
            round(
                sum(hr_recoveries)
                / len(hr_recoveries),
                1,
            )
            if hr_recoveries
            else None
        ),
    }

def _workout_progression_item(
    workout: Workout,
    analysis: WorkoutAnalysis | None,
) -> dict | None:
    if (
        analysis is None
        or not analysis.metrics_json
    ):
        return None

    try:
        metrics = json.loads(
            analysis.metrics_json
        )
    except json.JSONDecodeError:
        return None

    phase_metrics = (
        metrics.get("phase_metrics") or {}
    )

    phases = (
        phase_metrics.get("phases") or []
    )

    interval_recovery = (
        phase_metrics.get("interval_recovery")
        or []
    )

    interval = _interval_work_metrics(
        phases,
        interval_recovery,
    )

    if interval is not None:
        return {
            "date":
                workout.scheduled_date.isoformat(),
            "name":
                workout.name,
            "type":
                "interval",
            "metrics":
                interval,
        }

    continuous = _continuous_work_metrics(
        phases
    )

    if continuous is not None:
        return {
            "date":
                workout.scheduled_date.isoformat(),
            "name":
                workout.name,
            "type":
                "continuous",
            "metrics":
                continuous,
        }

    return None

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

def _completion_metrics(
    workouts: list[Workout],
    *,
    as_of: date,
) -> dict:
    planned = len(workouts)

    completed = sum(
        1
        for workout in workouts
        if workout.status == "completed"
    )

    missed = sum(
        1
        for workout in workouts
        if workout.status == "missed"
    )

    skipped = sum(
        1
        for workout in workouts
        if workout.status == "skipped"
    )

    open_workouts = sum(
        1
        for workout in workouts
        if workout.status == "planned"
    )

    due_workouts = [
        workout
        for workout in workouts
        if (
            workout.scheduled_date < as_of
            or workout.status
            in {
                "completed",
                "missed",
                "skipped",
            }
        )
    ]

    due = len(due_workouts)

    due_completed = sum(
        1
        for workout in due_workouts
        if workout.status == "completed"
    )

    return {
        "planned": planned,
        "due": due,
        "completed": completed,
        "missed": missed,
        "skipped": skipped,
        "open": open_workouts,
        "completion_percent": (
            round(
                due_completed / due * 100,
                1,
            )
            if due
            else None
        ),
    }

def _weekly_completion_metrics(
    workouts: list[Workout],
    *,
    as_of: date,
) -> list[dict]:
    weeks: dict[
        tuple[int, int],
        list[Workout],
    ] = {}

    for workout in workouts:
        iso = workout.scheduled_date.isocalendar()

        key = (
            iso.year,
            iso.week,
        )

        weeks.setdefault(
            key,
            [],
        ).append(workout)

    result = []

    for (year, week), items in sorted(
        weeks.items()
    ):
        metrics = _completion_metrics(
            items,
            as_of=as_of,
        )

        result.append(
            {
                "week": f"{year}-W{week:02d}",
                **metrics,
            }
        )

    return result


def build_monthly_review_input(
    year: int,
    month: int,
) -> dict:
    start, end = _month_range(
        year,
        month,
    )
    today = date.today()

    as_of = min(
        today,
        end - timedelta(days=1),
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

        free_activities = get_free_activities(
            session,
            start,
            end,
        )

        free_activity_items = [
            serialize_free_activity(
                activity,
                get_free_activity_analysis(
                    session,
                    activity,
                ),
            )
            for activity in free_activities
        ]

        completed = 0
        skipped = 0
        missed = 0
        planned = 0

        total_duration_seconds = 0.0
        total_distance_meters = 0.0

        workout_items = []
        training_progression = []

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

            progression_item = _workout_progression_item(
                workout,
                analysis,
            )

            if progression_item is not None:
                training_progression.append(
                    progression_item
                )

        for activity in free_activities:
            if activity.duration_seconds is not None:
                total_duration_seconds += (
                    activity.duration_seconds
                )

            if activity.distance_meters is not None:
                total_distance_meters += (
                    activity.distance_meters
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
                    "prompt_version":
                        review.prompt_version,
                    "model":
                        review.model,
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

            completion_metrics = _completion_metrics(
                workouts,
                as_of=as_of,
            )

            weekly_completion_metrics = (
                _weekly_completion_metrics(
                    workouts,
                    as_of=as_of,
                )
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
                "missed_workouts":
                    missed,
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
                 "free_activities":
                    len(free_activities),
                 "total_training_sessions":
                    completed + len(free_activities),
            },
            "monthly_metrics": {
                "completion":
                    completion_metrics,
                "weekly_completion":
                    weekly_completion_metrics,
                "training_volume": {
                    "duration_minutes": round(
                        total_duration_seconds / 60,
                        1,
                    ),
                    "distance_km": round(
                        total_distance_meters / 1000,
                        2,
                    ),
                    "completed_planned_sessions":
                        completed,
                    "free_sessions":
                        len(free_activities),
                    "total_training_sessions":
                        completed + len(free_activities),
                },
                "training_progression":
                    training_progression,
            },
            "weekly_reviews":
                weekly_reviews,
            "workouts":
                workout_items,
            "free_activities":
                free_activity_items,
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

MONTHLY_METRICS enthält deterministisch berechnete
Kennzahlen für den gesamten Trainingsmonat.

completion beschreibt den Trainingsplan des Monats
und die bis zum Stichtag bewertbare Planumsetzung.

planned bezeichnet alle für den Monat geplanten
Workouts.

due bezeichnet die bis zum Stichtag bereits fälligen
oder bereits abgeschlossenen, ausgelassenen bzw.
verpassten Workouts.

open bezeichnet weiterhin offene geplante Workouts.

completion_percent wird ausschließlich aus den
bereits fälligen Einheiten berechnet. Zukünftige
offene Workouts verschlechtern diese Quote nicht.

weekly_completion enthält dieselben Kennzahlen
getrennt nach den tatsächlich vorhandenen
Kalenderwochen.

Zukünftige Wochen mit due=0 dürfen nicht als
0-Prozent-Wochen oder als Verschlechterung der
Trainingskonsistenz interpretiert werden.

Nutze weekly_completion, um Veränderungen der
Trainingskonsistenz im Monatsverlauf zu beurteilen.
Beziehe dich dabei auf konkrete bereits bewertbare
Kalenderwochen und nicht auf künstlich gebildete
Monatsabschnitte.

Nutze konkrete Zahlen, wenn sie eine Entwicklung
verständlich machen. Eine Verbesserung der
Planumsetzung darf beispielsweise beschrieben werden,
wenn mehrere aufeinanderfolgende Kalenderwochen dies
tatsächlich zeigen.

training_volume beschreibt den tatsächlich
absolvierten Trainingsumfang.

training_progression enthält deterministisch aus den
sekündlichen Trainingsdaten abgeleitete Kennzahlen
der absolvierten Einheiten.

Bei type=continuous beziehen sich die Werte auf den
tatsächlichen Hauptteil der Einheit und nicht auf den
Durchschnitt der gesamten Aktivität.

Vergleiche absolute Leistungswerte nur dann direkt,
wenn Trainingsart, Zielbereich und Struktur ausreichend
vergleichbar sind. Eine niedrigere Leistung bei einem
bewusst niedrigeren Zielbereich ist keine
Verschlechterung.

power_target_status beschreibt, ob die
Durchschnittsleistung des Hauptteils innerhalb,
unterhalb oder oberhalb des geplanten Zielbereichs lag.

power_trend beschreibt die Leistungsentwicklung
innerhalb des jeweiligen Hauptteils. Verwende
wiederkehrende Veränderungen dieses Merkmals, um
Aussagen über die Stabilität der Trainingsausführung
im Monatsverlauf zu begründen.

Bei type=interval beschreiben work_in_target,
work_below_target und work_above_target die
Zielgenauigkeit der tatsächlichen Arbeitsintervalle.

recovery_in_target, recovery_below_target und
recovery_above_target beschreiben entsprechend die
Leistungssteuerung der geplanten Erholungsphasen.

Nutze diese Daten, um Entwicklungen zwischen
vergleichbaren Einheiten zu erkennen. Behaupte keinen
Leistungsfortschritt allein aufgrund steigender
absoluter Wattwerte.

heart_rate_trend beschreibt den Herzfrequenzverlauf
innerhalb einer Einheit und ist nicht gleichbedeutend
mit einer Bewertung der Trainingsreaktion als gut oder
schlecht.

Formuliere insbesondere nicht, die Herzfrequenz sei
stabil gewesen, wenn die zugrunde liegenden
heart_rate_trend-Werte überwiegend rising sind.

Technische heart_rate_drift-Werte dienen als
Hintergrund für die Bewertung. Nenne sie im
nutzerseitigen Monatsbericht nur dann numerisch,
wenn der konkrete Zahlenwert für die
Trainingssteuerung relevant ist.

Bevorzuge ansonsten verständliche Formulierungen wie
"die Herzfrequenz stieg im Verlauf trotz stabiler
Leistung an".

Wiederhole die Kennzahlen nicht lediglich als Liste,
sondern nutze sie zur Begründung der Monatsbewertung.

Eine Monatsanalyse soll Entwicklungen und Muster
herausarbeiten und nicht lediglich die Wochenreviews
und Einzelanalysen zusammenfassen.

Begründe zentrale Aussagen nach Möglichkeit mit
konkreten Zahlen oder mehreren übereinstimmenden
Beobachtungen aus dem Monatsverlauf.

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

Die Wochenreviews sind die primäre Grundlage für
wochenübergreifende Recovery- und Belastungstrends.

Recovery-Hinweise in Einzelanalysen können bereits
in den zugehörigen Wochenreviews berücksichtigt
worden sein. Werte denselben zugrunde liegenden
Recovery-Hinweis deshalb nicht erneut als
unabhängige Evidenz.

Ein recovery_assessment=watch in einer einzelnen
Woche ist ein Beobachtungspunkt und nicht automatisch
ein Regenerationsproblem des gesamten Monats.

Für recovery_assessment=concerning auf Monatsebene
sind wiederkehrende oder anhaltende auffällige
Recovery-Muster über mehrere Wochen erforderlich
oder ein besonders deutliches Muster zusammen mit
wiederkehrend auffälligen Trainingsreaktionen.

Mehrere Wochen mit recovery_assessment=good oder
unauffälligen Trainingsreaktionen dürfen als
gegenläufige Evidenz berücksichtigt werden.

Wenn eine Woche nur teilweise innerhalb des
betrachteten Monats liegt oder unvollständig
beobachtet wurde, interpretiere sie entsprechend
vorsichtig.

Nimm aus Schlaf-, HRV-, Ruhepuls- oder
Regenerationshinweisen keine medizinischen
Diagnosen vor.

Nimm selbst keine Änderungen an einem bestehenden
Trainingsplan vor.

Die Empfehlung soll eine Grundlage für die
Trainingsplanung des Folgemonats bilden.

FREE_ACTIVITIES enthält absolvierte Ruderaktivitäten,
die keinem geplanten Workout zugeordnet sind.

Diese freien Einheiten zählen zur tatsächlichen
Trainingsbelastung, Trainingsdauer und Distanz des
Monats.

Sie zählen NICHT als absolvierte geplante Workouts und
dürfen deshalb Planerfüllung oder Konsistenz der
Planumsetzung nicht künstlich verbessern.

Berücksichtige freie Einheiten insbesondere bei
load_assessment, training_volume und der Bewertung der
gesamten Monatsbelastung.

Bewerte bei freien Einheiten nicht die Einhaltung
geplanter Watt-, SPM-, Intervall- oder sonstiger
Trainingsvorgaben, da keine solchen Vorgaben existieren.

FREE_ACTIVITIES können eine analysis enthalten.

Wenn eine Analyse vorhanden ist, berücksichtige
deren load_assessment, effort, progression,
recovery_concern und summary bei der Bewertung
der tatsächlichen Trainingsbelastung.

Freie Trainings zählen zur tatsächlichen
Trainingsbelastung und können für Belastungs-,
Recovery- und Entwicklungstrends relevant sein.

Sie zählen jedoch weiterhin NICHT als Erfüllung
eines geplanten Workouts.

Leite aus zusätzlichen freien Trainings nicht
automatisch eine höhere zukünftige
Trainingskapazität ab.

Ein höheres tatsächliches Trainingsvolumen
rechtfertigt für sich allein keine Erhöhung des
geplanten Trainingsumfangs.

Bei einem noch laufenden Monat dürfen geplante,
aber noch nicht fällige Workouts nicht negativ in
consistency, assessment, trend oder load_assessment
eingehen.

Workouts mit status="planned" sind offene Einheiten.
Sie sind weder missed noch skipped und dürfen nicht
als fehlende Planumsetzung bewertet werden.

Insbesondere dürfen zukünftige Kalenderwochen mit
noch offenen geplanten Workouts nicht als Wochen mit
0 % Planerfüllung oder als Rückgang der Konsistenz
interpretiert werden.

Bewerte die bisherige Planumsetzung eines laufenden
Monats ausschließlich anhand bereits fälliger
Einheiten.

Wenn ein wesentlicher Teil des Monats noch offen ist
und deshalb keine belastbare Aussage über Konsistenz,
Trend oder Gesamtbelastung möglich ist, verwende
"unknown", "unclear" oder "unknown" entsprechend
der jeweiligen Ausgabekategorie.

Ein niedriger bisheriger Trainingsumfang zu Beginn
eines laufenden Monats ist nicht automatisch eine
zu niedrige Monatsbelastung.

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
