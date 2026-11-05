import json
import os

from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel

from typing import Literal
from database.engine import SessionLocal
from database.models import (
    Activity,
    WorkoutActivityLink,
    WorkoutAnalysis,
)
from endurain_client import EndurainClient
from workout_phase_analyzer import (
    analyze_free_activity_metrics,
    analyze_workout_phases,
)
from stream_signal_quality import (
    clean_activity_streams,
)
from recovery_context import (
    build_recovery_context,
)
from heart_rate_zones import (
    get_configured_heart_rate_zones,
)


MODEL = "gpt-6-luna"
PROMPT_VERSION = "9"


class WorkoutAnalysisResult(BaseModel):
    execution: Literal[
        "good",
        "partial",
        "poor",
        "unknown",
    ]

    load_assessment: Literal[
        "low",
        "appropriate",
        "high",
        "unknown",
    ]

    effort: Literal[
        "easy",
        "moderate",
        "hard",
        "unknown",
    ]

    progression: Literal[
        "positive",
        "stable",
        "concerning",
        "unknown",
    ]

    recovery_concern: bool
    summary: str
    recommendation: str

def analyze_endurain_activity(
    endurain_activity_id: int,
) -> WorkoutAnalysis:
    with SessionLocal() as session:
        activity = (
            session.query(Activity)
            .filter(
                Activity.endurain_activity_id
                == endurain_activity_id
            )
            .first()
        )

        if activity is None:
            raise RuntimeError(
                "Endurain activity "
                f"{endurain_activity_id} not found"
            )

        link = (
            session.query(WorkoutActivityLink)
            .filter(
                WorkoutActivityLink.activity_id
                == activity.id
            )
            .first()
        )

        if link is None:
            return analyze_free_activity(
                endurain_activity_id
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

    sleep_records = client.get_sleep_records()

    workout_date = datetime.fromisoformat(
        planned["date"]
    ).date()

    data["recovery_context"] = (
        build_recovery_context(
            sleep_records,
            workout_date,
        )
    )

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

    heart_rate_zones = (
        get_configured_heart_rate_zones()
    )

    data["phase_metrics"] = (
        analyze_workout_phases(
            warmup=planned["warmup"],
            repeat=planned["repeat"],
            work=planned["work"],
            recovery=planned["recovery"],
            cooldown=planned["cooldown"],
            streams=streams,
            heart_rate_zones=
                heart_rate_zones,
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

def build_free_activity_analysis_input(
    endurain_activity_id: int,
) -> dict:
    with SessionLocal() as session:
        activity = (
            session.query(Activity)
            .filter(
                Activity.endurain_activity_id
                == endurain_activity_id
            )
            .first()
        )

        if activity is None:
            raise RuntimeError(
                "Endurain activity "
                f"{endurain_activity_id} not found"
            )

        if activity.workout_links:
            raise RuntimeError(
                "Activity is linked to a planned "
                "workout and is not a free activity"
            )

        activity_date = activity.start_time.date()

        actual_activity = {
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
        }

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

    heart_rate_zones = (
        get_configured_heart_rate_zones()
    )

    activity_metrics = (
        analyze_free_activity_metrics(
            streams=cleaned.streams,
            heart_rate_zones=
                heart_rate_zones,
        )
    )

    sleep_records = client.get_sleep_records()

    return {
        "activity_type": "free",
        "planned_workout": None,
        "actual_activity": actual_activity,
        "recovery_context":
            build_recovery_context(
                sleep_records,
                activity_date,
            ),
        "data_quality": {
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
        },
        "activity_metrics":
             activity_metrics,
    }

def analyze_free_activity(
    endurain_activity_id: int,
) -> WorkoutAnalysis:
    with SessionLocal() as session:
        activity = (
            session.query(Activity)
            .filter(
                Activity.endurain_activity_id
                == endurain_activity_id
            )
            .first()
        )

        if activity is None:
            raise RuntimeError(
                "Endurain activity "
                f"{endurain_activity_id} not found"
            )

        if activity.workout_links:
            raise RuntimeError(
                "Activity is linked to a planned "
                "workout and is not a free activity"
            )

        existing = (
            session.query(WorkoutAnalysis)
            .filter(
                WorkoutAnalysis.activity_id
                == activity.id,
                WorkoutAnalysis.workout_id.is_(None),
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

        activity_id = activity.id

    input_data = (
        build_free_activity_analysis_input(
            endurain_activity_id
        )
    )

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"]
    )

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """
Du bist ein Trainingscoach für Indoor-Rudern.

Analysiere genau eine frei absolvierte
Rudereinheit.

Für diese Einheit existiert keine geplante
Trainingsvorgabe.

Bewerte deshalb NICHT, ob Watt-, Dauer-,
Intervall- oder Schlagzahlvorgaben erfüllt
wurden.

execution muss für freie Trainings immer
"unknown" sein.

Bewerte stattdessen die tatsächlich
entstandene Trainingsbelastung.

Berücksichtige insbesondere:
- Dauer und Distanz
- average_power und normalized_power
- durchschnittliche und maximale Herzfrequenz
- Schlagzahl
- persönliche Herzfrequenzbereiche
- Datenqualität
- Recovery-Kontext

ACTIVITY_METRICS enthält deterministisch aus
den bereinigten Endurain-Streams berechnete
Werte für die gesamte freie Einheit.

power_trend und heart_rate_trend beschreiben
den zeitlichen Verlauf der Einheit.

heart_rate_zones enthält die tatsächliche
Verteilung der Herzfrequenz über die persönlich
konfigurierten Bereiche.

heart_rate_drift_percent darf nur dann als
kardiovaskuläre Drift interpretiert werden,
wenn heart_rate_drift_interpretable=true ist.

Bei heart_rate_drift_interpretable=false darf
aus dem Drift-Wert keine entsprechende
Bewertung abgeleitet werden.

Bewerte eine höhere Herzfrequenzzone nicht
isoliert als zu hohe Belastung. Berücksichtige
Leistung, Leistungsverlauf, Dauer und
Recovery-Kontext gemeinsam.

Die intern berechneten first_half_* und
second_half_* Werte dienen ausschließlich der
Verlaufsanalyse. Bezeichne sie im nutzerseitigen
Text nicht als erste oder zweite Hälfte.
Formuliere stattdessen beispielsweise
"im Verlauf der Einheit" oder
"gegen Ende der Einheit".

load_assessment beschreibt, ob die Belastung
dieser zusätzlichen Einheit im vorhandenen
Kontext niedrig, angemessen, hoch oder nicht
beurteilbar erscheint.

effort beschreibt den Charakter der
tatsächlichen Belastung:
- easy
- moderate
- hard
- unknown

progression darf aus einer einzelnen freien
Einheit keine langfristige Entwicklung
ableiten.

Eine freie Einheit ist zusätzliche tatsächliche
Trainingsbelastung. Sie erfüllt jedoch nicht
automatisch ein geplantes Workout.

Recovery-Daten sind zusätzlicher Kontext und
keine medizinische Diagnose.

Ein einzelner auffälliger Recovery-Wert darf
nicht automatisch zu recovery_concern=true
führen.

Die Analyse soll sachlich, knapp und auf die
Trainingssteuerung ausgerichtet sein.

recommendation beschreibt die Konsequenz für
die nächsten Einheiten, ohne selbst den
Trainingsplan zu verändern.
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
            "OpenAI returned no free activity "
            "analysis"
        )

    # Freie Trainings besitzen per Definition
    # keine Soll-Ausführung.
    result.execution = "unknown"

    with SessionLocal() as session:
        analysis = WorkoutAnalysis(
            workout_id=None,
            activity_id=activity_id,
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
            metrics_json=json.dumps(
                {
                    "data_quality":
                        input_data.get(
                            "data_quality"
                        ),
                    "activity_metrics":
                        input_data.get(
                            "activity_metrics"
                        ),
                },
                ensure_ascii=False,
            ),
            model=MODEL,
            prompt_version=PROMPT_VERSION,
        )

        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        return analysis

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

first_half_average_power, second_half_average_power,
first_half_average_hr und second_half_average_hr sind
ausschließlich interne Vergleichswerte zur Beurteilung
des zeitlichen Verlaufs innerhalb einer Trainingsphase.

Bezeichne diese Werte in summary, recommendation oder
anderen nutzerseitigen Texten NICHT als "erste Hälfte",
"zweite Hälfte", "zwischen den Hälften" oder als
eigenständige Trainingsabschnitte.

Bei einer einzelnen kontinuierlichen work-Phase
beschreibe stattdessen den zeitlichen Verlauf, zum
Beispiel mit Formulierungen wie:
- "im Verlauf des Hauptteils"
- "gegen Ende des Hauptteils"
- "über den Hauptteil hinweg"
- "die Leistung blieb über den Hauptteil stabil"

Nur tatsächlich im Trainingsplan vorhandene Phasen,
Intervalle oder Wiederholungen dürfen als Abschnitte,
Intervalle oder Wiederholungen bezeichnet werden.

Bei Intervalltrainings beziehe dich auf die tatsächlich
vorhandenen work_1, work_2, ... und recovery_1,
recovery_2, ... Phasen. Verwende auch dort die internen
first_half_* und second_half_* Werte nur zur Beurteilung
des Verlaufs INNERHALB des jeweiligen Intervalls und
nicht als Bezeichnung zusätzlicher Trainingsabschnitte.

power_trend ist eine deterministisch berechnete
Beschreibung des Leistungsverlaufs innerhalb einer
Phase:
- stable: Leistung blieb im Verlauf weitgehend stabil
- rising: Leistung nahm im Verlauf zu
- falling: Leistung nahm im Verlauf ab
- unknown: keine belastbare Aussage möglich

heart_rate_trend beschreibt entsprechend ausschließlich
die zeitliche Richtung der Herzfrequenzentwicklung:
- stable
- rising
- falling
- unknown

Diese Trendfelder sind für die nutzerseitige
Formulierung gegenüber den technischen first_half_*
und second_half_* Feldern zu bevorzugen.

Die Trendwerte sind deskriptiv und stellen für sich
allein keine Bewertung als gut oder schlecht dar.

heart_rate_zones enthält die deterministisch aus den
persönlich konfigurierten Herzfrequenzbereichen
berechnete Verteilung der Herzfrequenz innerhalb der
jeweiligen tatsächlichen Trainingsphase.

Die Zonen basieren auf dem persönlichen Athletenprofil.
Bei der aktuell verwendeten Methode max_hr entsprechen
sie prozentualen Bereichen der individuell
konfigurierten maximalen Herzfrequenz.

distribution enthält für jede Zone die Dauer in
Sekunden und den prozentualen Anteil der Phase.
dominant_zone bezeichnet die Zone mit dem größten
Zeitanteil.

Die Zonen sind eine Beschreibung der physiologischen
Beanspruchung und nicht automatisch eine Bewertung der
Trainingsausführung.

Leite insbesondere NICHT allein aus einem Aufenthalt in
einer höheren Herzfrequenzzone ab, dass eine Einheit zu
hart oder schlecht ausgeführt wurde.

Bewerte die Herzfrequenzzonen zusammen mit:
- Trainingsart und geplanter Struktur
- Leistung und Leistungsvorgabe
- power_trend
- heart_rate_trend
- sofern interpretierbar der Herzfrequenzdrift
- bei Intervallen der Herzfrequenzerholung
- dem Recovery-Kontext

Bei kontinuierlichen Einheiten kann eine Verschiebung
der Herzfrequenz in höhere Zonen bei gleichzeitig
stabiler Leistung eine zunehmende kardiovaskuläre
Beanspruchung im Verlauf anzeigen.

Formuliere dies zunächst deskriptiv. Eine solche
Verschiebung ist für sich allein weder ein
Regenerationsproblem noch eine schlechte
Trainingsausführung.

Bei kurzen Arbeitsintervallen ist zu berücksichtigen,
dass die Herzfrequenz verzögert auf eine Änderung der
Belastung reagiert. Die Herzfrequenzzone eines einzelnen
kurzen Intervalls darf deshalb nicht isoliert zur
Bewertung seiner Intensität verwendet werden.

Bei Recovery-Phasen ist die Veränderung der
Herzfrequenz und INTERVAL_RECOVERY aussagekräftiger als
die dominante Herzfrequenzzone allein.

below_zone und above_zone beschreiben Messwerte
außerhalb der konfigurierten Zonen. Sie sind nicht
automatisch als auffällig zu bewerten.

Nutze konkrete Zonenanteile nur dann im nutzerseitigen
Text, wenn sie für die Beurteilung der Einheit relevant
sind. Wiederhole nicht lediglich die vollständige
Zonenverteilung.

Wenn bei einer kontinuierlichen work-Phase die Leistung
im Zielbereich und weitgehend stabil bleibt, während
sich die Herzfrequenz im Verlauf erkennbar in höhere
Zonen verschiebt, nenne die wesentlichen Zonenanteile,
wenn sie die zunehmende kardiovaskuläre Beanspruchung
konkret verständlich machen.

Beispielsweise kann bei überwiegendem Aufenthalt in
zone_2 mit einem relevanten Anteil in zone_3 beschrieben
werden, dass die Einheit überwiegend im leichteren
Herzfrequenzbereich lag, die kardiovaskuläre
Beanspruchung im Verlauf jedoch zunahm.

Bewerte einen solchen zone_3-Anteil nicht automatisch
als zu hohe Intensität. Entscheidend ist der
Zusammenhang mit Leistungsvorgabe, Leistungsverlauf,
Herzfrequenzverlauf und Trainingsart.

heart_rate_drift_bpm und heart_rate_drift_percent
beschreiben die Veränderung der Herzfrequenz im
zeitlichen Verlauf einer Phase. Die Berechnung
vergleicht intern einen früheren mit einem späteren
Teil der Phase.

Beschreibe dies im nutzerseitigen Text als Entwicklung
"im Verlauf", "über die Phase hinweg" oder "gegen Ende"
der jeweiligen Phase und nicht als Vergleich zweier
Hälften.

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

RECOVERY_CONTEXT enthält Gesundheits- und
Erholungsdaten aus der Nacht vor dem Training sowie
persönliche Baselines aus vorherigen Tagen.

Diese Daten sind zusätzlicher Trainingskontext und
keine medizinische Diagnose.

sleep.duration_minutes beschreibt die Schlafdauer
der Nacht vor dem Training.
sleep.baseline_7d_minutes beschreibt die persönliche
Schlaf-Baseline der vorherigen sieben Kalendertage.
sleep.deviation_minutes beschreibt die Abweichung
davon.

sleep.score ist der aktuelle Sleep Score.
sleep.score_baseline_7d ist die persönliche
7-Tage-Baseline dieses Scores.

resting_heart_rate.bpm ist der aktuelle Ruhepuls.
resting_heart_rate.baseline_28d_bpm ist die
persönliche 28-Tage-Baseline.
resting_heart_rate.deviation_bpm beschreibt die
Abweichung davon.

hrv.status ist ein vom Quellsystem bereitgestellter
HRV-Status. LOW oder UNBALANCED darf NICHT isoliert
als Hinweis auf unzureichende Regeneration gewertet
werden. Berücksichtige, dass ein solcher Status auch
Teil des persönlichen längerfristigen Verlaufs sein
kann.

sleep_stress.value ist der Schlaf-Stresswert.
sleep_stress.baseline_7d ist die persönliche
7-Tage-Baseline und sleep_stress.deviation die
Abweichung davon.

Bewerte Recovery-Werte primär relativ zu den
persönlichen Baselines und nicht anhand allgemeiner
pauschaler Grenzwerte.

Ein einzelner schlechter Schlafwert, ein niedriger
Sleep Score, ein erhöhter Ruhepuls, ein HRV-Status
LOW oder UNBALANCED oder ein auffälliger
Sleep-Stresswert darf allein NICHT zu
recovery_concern=true führen.

Mehrere auffällige Kennzahlen derselben Nacht sind nicht
automatisch mehrere unabhängige Recovery-Signale.

Schlafdauer, Sleep Score, HRV-Status, Ruhepuls und
Sleep-Stress können miteinander zusammenhängen und
dürfen nicht allein durch ihre Anzahl zu
recovery_concern=true führen.

Wenn die Trainingsreaktion trotz solcher nächtlichen
Hinweise unauffällig ist, insbesondere wenn Leistung,
Herzfrequenzverlauf und bei Intervallen die
Herzfrequenzerholung keine konsistent auffällige
Reaktion zeigen, soll recovery_concern grundsätzlich
false bleiben.

recovery_concern=true erfordert entweder eine zur
Recovery-Situation passende auffällige Trainingsreaktion
oder ein deutliches, über mehrere Tage erkennbares
Recovery-Muster.

Eine normale oder gute Trainingsausführung, stabile
Leistung und unauffällige Herzfrequenzerholung dürfen
als gegenläufige Evidenz berücksichtigt werden.

Wenn RECOVERY_CONTEXT fehlt oder einzelne Werte null
sind, dürfen daraus keine negativen Schlussfolgerungen
gezogen werden.

Formuliere aus Schlaf-, HRV-, Ruhepuls- oder
Stressdaten keine medizinischen Diagnosen.

power_in_target_percent basiert auf sekündlicher
Instantanleistung. Bei einem engen Watt-Zielbereich
darf ein niedriger Wert allein NICHT als schlechte
Ausführung bewertet werden. Berücksichtige
insbesondere Phasendurchschnitt, Leistungsstreuung
und den Leistungsverlauf innerhalb der Phase.
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
            metrics_json=json.dumps(
                {
                    "data_quality":
                        input_data.get("data_quality"),
                    "phase_metrics":
                        input_data.get("phase_metrics"),
                },
                ensure_ascii=False,
            ),
            model=MODEL,
            prompt_version=PROMPT_VERSION,
        )

        session.add(analysis)
        session.commit()
        session.refresh(analysis)

        return analysis