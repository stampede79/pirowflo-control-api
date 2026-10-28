import json
import os

from openai import OpenAI
from pydantic import BaseModel

from database.engine import SessionLocal
from database.models import (
    WorkoutActivityLink,
    WorkoutAnalysis,
)
from endurain_client import EndurainClient
from workout_phase_analyzer import (
    analyze_workout_phases,
)
from stream_signal_quality import (
    clean_activity_streams,
)

MODEL = "gpt-6-luna"
PROMPT_VERSION = "4"


class WorkoutAnalysisResult(BaseModel):
    execution: str
    load_assessment: str
    effort: str
    progression: str
    recovery_concern: bool
    summary: str
    recommendation: str

def analyze_endurain_activity(
    endurain_activity_id: int,
) -> WorkoutAnalysis:
    with SessionLocal() as session:
        link = (
            session.query(WorkoutActivityLink)
            .join(WorkoutActivityLink.activity)
            .filter(
                WorkoutActivityLink.activity.has(
                    endurain_activity_id=
                        endurain_activity_id
                )
            )
            .first()
        )

        if link is None:
            raise RuntimeError(
                "No confirmed workout link for "
                f"Endurain activity "
                f"{endurain_activity_id}"
            )

        link_id = link.id

    return analyze_workout(link_id)

def build_detailed_workout_analysis_input(
    endurain_activity_id: int,
) -> dict:
    data = build_workout_analysis_input(
        endurain_activity_id
    )

    client = EndurainClient(
        server=os.environ["ENDURAIN_SERVER"],
        username=os.environ[
            "ENDURAIN_USERNAME"
        ],
        password=os.environ[
            "ENDURAIN_PASSWORD"
        ],
    )

    streams = client.get_activity_streams(
        endurain_activity_id
    )

    cleaned = clean_activity_streams(
        streams
    )

    streams = cleaned.streams

    planned = data["planned_workout"]

    data["data_quality"] = {
        name: {
            "raw_samples":
                quality.raw_samples,
            "clean_samples":
                quality.clean_samples,
            "excluded_samples":
                quality.excluded_samples,
            "excluded_percent":
                quality.excluded_percent,
            "quality":
                quality.quality,
        }
        for name, quality
        in cleaned.quality.items()
    }
    # V2 zunächst nur für nicht-intervallartige Einheiten.
    data["phase_metrics"] = (
    analyze_workout_phases(
        warmup=planned["warmup"],
        repeat=planned["repeat"],
        work=planned["work"],
        recovery=planned["recovery"],
        cooldown=planned["cooldown"],
        streams=streams,
    )
)

    return data

def build_workout_analysis_input(
    endurain_activity_id: int,
) -> dict:
    with SessionLocal() as session:
        link = (
            session.query(WorkoutActivityLink)
            .join(WorkoutActivityLink.activity)
            .filter(
                WorkoutActivityLink.activity.has(
                    endurain_activity_id=
                        endurain_activity_id
                )
            )
            .first()
        )

        if link is None:
            raise RuntimeError(
                "No workout link for Endurain "
                f"activity {endurain_activity_id}"
            )

        workout = link.workout
        activity = link.activity

        return {
            "planned_workout": {
                "date":
                    workout.scheduled_date.isoformat(),
                "name":
                    workout.name,
                "description":
                    workout.description,
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
            "actual_activity": {
                "endurain_activity_id":
                    activity.endurain_activity_id,
                "start_time":
                    activity.start_time.isoformat(),
                "duration_minutes": (
                    round(
                        activity.duration_seconds / 60,
                        1,
                    )
                    if activity.duration_seconds
                    is not None
                    else None
                ),
                "distance_km": (
                    round(
                        activity.distance_meters / 1000,
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
            },
        }

def analyze_workout(
    link_id: int,
) -> WorkoutAnalysis:
    with SessionLocal() as session:
        link = session.get(
            WorkoutActivityLink,
            link_id,
        )

        if link is None:
            raise RuntimeError(
                f"Workout activity link "
                f"{link_id} not found"
            )

        workout = link.workout
        activity = link.activity

        existing = (
            session.query(WorkoutAnalysis)
            .filter(
                WorkoutAnalysis.activity_id
                == activity.id,
                WorkoutAnalysis.workout_id
                == workout.id,
                WorkoutAnalysis.model
                == MODEL,
                WorkoutAnalysis.prompt_version
                == PROMPT_VERSION,
            )
            .order_by(
                WorkoutAnalysis.created_at.desc()
            )
            .first()
        )

        if existing is not None:
            return existing

        input_data = build_detailed_workout_analysis_input(
    activity.endurain_activity_id
)

        client = OpenAI(
            api_key=os.environ[
                "OPENAI_API_KEY"
            ],
        )

        response = client.responses.parse(
            model=MODEL,
            input=[
                {
                    "role": "system",
                    "content": """
Du bist ein Trainingscoach für Indoor-Rudern.

Analysiere genau eine absolvierte Trainingseinheit
im Vergleich mit dem geplanten Training.

Wichtig:

Die Durchschnittsleistung der Aktivität umfasst
Warm-up, Hauptteil, Erholungsphasen und Cool-down.
Vergleiche average_power deshalb NICHT direkt mit
dem Wattziel des Hauptteils.

normalized_power kann als zusätzliche Information
zur Belastung verwendet werden.

Bewerte keine langfristige Entwicklung anhand einer
einzelnen Einheit. progression beschreibt nur, ob
diese Einheit im vorhandenen Kontext unauffällig,
positiv oder auffällig erscheint.

Eine einzelne auffällige Einheit soll nicht
automatisch zu einer Planänderung führen.

Die Analyse soll sachlich, knapp und auf die
Trainingssteuerung ausgerichtet sein.

execution:
- good
- partial
- poor
- unknown

load_assessment:
- low
- appropriate
- high
- unknown

effort:
- easy
- moderate
- hard
- unknown

progression:
- positive
- stable
- concerning
- unknown

recovery_concern ist true nur bei einem konkreten
Hinweis darauf, dass Regeneration berücksichtigt
werden sollte.

recommendation beschreibt die Konsequenz für die
nächsten Einheiten, ohne selbst den Trainingsplan
zu verändern.

DATA_QUALITY beschreibt die Qualität der
zugrunde liegenden Endurain-Streams.

Offensichtliche Messartefakte wurden vor der
Berechnung von PHASE_METRICS deterministisch
ausgeschlossen.

excluded_samples und excluded_percent geben an,
wie viele Messwerte eines Signals verworfen wurden.

Bei quality=poor dürfen aus dem betroffenen Signal
keine belastbaren Schlussfolgerungen gezogen werden.
Bei quality=fair müssen Aussagen entsprechend
vorsichtig formuliert werden.

PHASE_METRICS enthält deterministisch aus den
sekündlichen Endurain-Streams berechnete Werte für
die einzelnen Trainingsphasen.

Wenn PHASE_METRICS vorhanden ist, hat die Bewertung
des Hauptteils anhand dieser Phasenwerte Vorrang vor
den Durchschnittswerten der Gesamtaktivität.

Bei Leistungsvorgaben ist average_power der
entsprechenden work-Phase besonders relevant.

first_half_average_power und
second_half_average_power zeigen, ob die Leistung
innerhalb der Phase stabil geblieben ist.

first_half_average_hr und second_half_average_hr
dürfen zur Beurteilung der kardiovaskulären
Belastungsentwicklung innerhalb der Einheit
herangezogen werden.

first_half_average_hr und second_half_average_hr
dürfen zur Beurteilung der kardiovaskulären
Belastungsentwicklung innerhalb der Einheit
herangezogen werden.

heart_rate_drift_bpm und heart_rate_drift_percent
beschreiben die Veränderung der Herzfrequenz zwischen
der ersten und zweiten Hälfte einer Phase.

heart_rate_drift_interpretable gibt deterministisch an,
ob diese Veränderung als HF-Drift sinnvoll interpretiert
werden kann.

Nur wenn heart_rate_drift_interpretable=true ist, darf
heart_rate_drift_percent zur Beurteilung einer
kardiovaskulären Drift herangezogen werden.

Bei heart_rate_drift_interpretable=false darf aus dem
Drift-Wert keine entsprechende Bewertung abgeleitet
werden.

INTERVAL_RECOVERY enthält bei Intervalltrainings
deterministisch berechnete Werte zur
Herzfrequenzerholung zwischen work- und
recovery-Phasen.

heart_rate_work_end ist die durchschnittliche
Herzfrequenz der letzten 30 Sekunden der
vorhergehenden work-Phase.

heart_rate_recovery_peak ist der höchste gleitende
5-Sekunden-Mittelwert innerhalb der ersten
30 Sekunden der recovery-Phase. Dadurch wird die
verzögerte Herzfrequenzreaktion nach Ende des
Arbeitsintervalls berücksichtigt.

heart_rate_recovery_end ist die durchschnittliche
Herzfrequenz der letzten 30 Sekunden der
recovery-Phase.

heart_rate_recovery_bpm beschreibt den Abfall von
heart_rate_recovery_peak zu heart_rate_recovery_end.

Bewerte heart_rate_recovery_bpm nicht anhand
pauschaler allgemeiner Grenzwerte als gut oder
schlecht. Vergleiche insbesondere die Recoveries
innerhalb derselben Einheit und berücksichtige
Belastung, Ausgangsherzfrequenz und Verlauf über
die Wiederholungen.

Ein einzelner auffälliger Recovery-Wert darf nicht
automatisch als Regenerationsproblem interpretiert
werden.

recovery_concern darf nicht allein deshalb true sein,
weil ein einzelner späterer heart_rate_recovery_bpm-Wert
niedriger als vorherige Werte ist.

Ein recovery_concern erfordert einen konsistenten
auffälligen Erholungsverlauf über mehrere Recoveries
oder einen zusätzlichen konkreten Hinweis auf
unzureichende Regeneration.

Ein nicht-monotoner Verlauf einzelner Recovery-Werte
reicht dafür nicht aus.

power_in_target_percent basiert auf sekündlicher
Instantanleistung. Bei einem engen Watt-Zielbereich
...

power_in_target_percent basiert auf sekündlicher
Instantanleistung. Bei einem engen Watt-Zielbereich
darf ein niedriger Wert allein NICHT als schlechte
Ausführung bewertet werden. Berücksichtige
insbesondere Phasendurchschnitt, Leistungsstreuung
und Stabilität zwischen erster und zweiter Hälfte.
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
            text_format=WorkoutAnalysisResult,
        )

        result = response.output_parsed

        if result is None:
            raise RuntimeError(
                "OpenAI returned no workout analysis"
            )

        analysis = WorkoutAnalysis(
            workout_id=workout.id,
            activity_id=activity.id,
            execution=result.execution,
            load_assessment=
                result.load_assessment,
            effort=result.effort,
            progression=result.progression,
            recovery_concern=
                result.recovery_concern,
            summary=result.summary,
            recommendation=
                result.recommendation,
            analysis_json=json.dumps(
                result.model_dump(),
                ensure_ascii=False,
            ),
            model=MODEL,
            prompt_version=PROMPT_VERSION,
        )

        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        return analysis