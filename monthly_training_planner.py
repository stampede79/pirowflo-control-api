import calendar
import json
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field
import hashlib

from monthly_planning_context import (
    build_monthly_planning_input,
)



MODEL = "gpt-6-luna"

PROMPT_VERSION = "2"

DRAFT_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)

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

def _cached_draft(
    *,
    target_year: int,
    target_month: int,
    fingerprint: str,
) -> Path | None:
    output_file = DRAFT_DIR / (
        f"{target_year:04d}-"
        f"{target_month:02d}.json"
    )

    if not output_file.exists():
        return None

    try:
        data = json.loads(
            output_file.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if (
        data.get("input_fingerprint")
        != fingerprint
    ):
        return None

    if data.get("model") != MODEL:
        return None

    if (
        data.get("prompt_version")
        != PROMPT_VERSION
    ):
        return None

    return output_file
class MonthlyPlanResult(BaseModel):
    path: str
    cache_hit: bool
    openai_calls: int
    input_fingerprint: str

class TrainingPlanWorkout(BaseModel):
    date: str
    name: str
    description: str
    warmup: str | None = None
    repeat: int = Field(default=1, ge=1, le=20)
    work: str
    recovery: str | None = None
    cooldown: str | None = None


class TrainingPlan(BaseModel):
    year: int
    month: int
    workouts: list[TrainingPlanWorkout]


def next_month(
    year: int,
    month: int,
) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1

    return year, month + 1


def month_name(
    year: int,
    month: int,
) -> str:
    names = [
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ]

    return f"{names[month]} {year}"


def generate_monthly_plan(
    *,
    target_year: int | None = None,
    target_month: int | None = None,
    now: datetime | None = None,
    sessions_per_week: int = 3,
) -> MonthlyPlanResult:
    if now is None:
        now = datetime.now()

    if (
        target_year is None
        or target_month is None
    ):
        target_year, target_month = next_month(
            now.year,
            now.month,
        )

    context = build_monthly_planning_input(
        target_year=target_year,
        target_month=target_month,
    )

    fingerprint = _input_fingerprint(
        context
    )

    cached = _cached_draft(
        target_year=target_year,
        target_month=target_month,
        fingerprint=fingerprint,
    )

    if cached is not None:
        return MonthlyPlanResult(
            path=str(cached),
            cache_hit=True,
            openai_calls=0,
            input_fingerprint=fingerprint,
        )

    target_name = month_name(
        target_year,
        target_month,
    )

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
    )

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": f"""
Du erstellst einen personalisierten Trainingsplan
für Indoor-Rudern.

Der Nutzer trainiert mit PiRowFlo und SmartRow.

Du erhältst einen strukturierten Planungsinput mit:

- den geplanten und absolvierten Trainings des
  Vormonats,
- tatsächlichen Leistungsdaten,
- Analysen einzelner Trainingseinheiten,
- Weekly Reviews,
- optional einem finalen Monthly Review,
- bestätigten Verfügbarkeitsentscheidungen,
- persönlichen Kalendereinträgen,
- deterministisch berechneten
  planning_constraints.

WICHTIGE PRIORITÄTEN:

1. planning_constraints haben bei der Terminwahl
   Vorrang.

2. Für jeden Eintrag in unavailable_dates darf
   KEIN Training geplant werden.

3. explicitly_available_dates dürfen trotz eines
   persönlichen Kalendereintrags für Training
   verwendet werden.

4. limited_dates dürfen nur für leichte oder
   zeitlich wenig belastende Einheiten verwendet
   werden, wenn dies trainingsfachlich sinnvoll ist.

5. Mehrtägige Abwesenheiten wurden bereits in
   planning_constraints berücksichtigt. Versuche
   nicht, diese Regeln neu zu interpretieren.

6. Persönliche Kalendereinträge ohne explizite
   Availability-Entscheidung sind Planungskontext,
   aber nicht automatisch ein Trainingsverbot.

TRAININGSDATEN:

status=completed bedeutet, dass das Training
abgeschlossen wurde.

status=planned bedeutet, dass das Training zum
Zeitpunkt der Planung noch bevorsteht. Es darf
NICHT als ausgelassen oder nicht absolviert
bewertet werden.

status=skipped bedeutet, dass das Training bewusst
ausgelassen wurde.

status=missed bedeutet, dass der Trainingstermin
bereits vergangen ist und keine passende Aktivität
gefunden wurde. Das Training gilt als nicht
absolviert.

Berücksichtige missed Trainings bei der Beurteilung
der bisherigen Planumsetzung. Einzelne missed
Trainings allein rechtfertigen jedoch keine
grundlegende Änderung der Trainingssteuerung.

Nutze die vorhandenen Workout-Analysen stärker als
bloße Durchschnittswerte.

Ein einzelnes auffälliges Training begründet keine
generelle Trainingsänderung. Wiederkehrende Muster
über mehrere Einheiten oder Reviews sind stärker zu
gewichten.

Wenn ein Monthly Review vorhanden ist, verwende ihn
als übergeordnete Bewertung des Vormonats.

Wenn noch kein Monthly Review vorhanden ist,
erstelle trotzdem einen konservativen Plan anhand
der vorhandenen Einzelanalysen und Weekly Reviews.

Berücksichtige noch geplante Trainingseinheiten am
Ende des Vormonats bei der Terminierung der ersten
Einheiten des Zielmonats. Behandle sie nicht als
bereits absolviert, plane aber ausreichende
Regeneration für den Fall, dass sie stattfinden.

TRAININGSSTEUERUNG:

Plane konservativ.

Steigere Umfang oder Intensität nur moderat und nur
wenn die vorhandenen Daten dies unterstützen.

Grundlagentraining soll den größten Anteil
ausmachen.

Plane die Belastung nicht monoton über den gesamten
Monat.

Berücksichtige leichtere Phasen bzw.
Regenerationsphasen, wenn die vorhandenen Daten
dafür sprechen.

Verwende ausschließlich Watt und SPM als
Trainingsziele.

Vermeide nach Möglichkeit Trainingseinheiten an
direkt aufeinanderfolgenden Tagen.

Plane {sessions_per_week} Einheiten pro Woche,
soweit Verfügbarkeit und Regeneration dies sinnvoll
zulassen. Eine Abwesenheitswoche muss nicht durch
zusätzliche Einheiten davor oder danach kompensiert
werden.

PiRowFlo-Format:

Dauer:
5m, 30m usw.

Leistung:
100-110w

Schlagzahl:
16-18spm

Kombination:
40m,105-110w,16-18spm

Erstelle ausschließlich Trainingseinheiten für
{target_name}.
""",
            },
            {
                "role": "user",
                "content": (
                    "Erstelle anhand dieses "
                    "Planungsinputs einen "
                    "personalisierten Trainingsplan "
                    f"für {target_name}.\n\n"
                    + json.dumps(
                        context,
                        ensure_ascii=False,
                        indent=2,
                    )
                ),
            },
        ],
        text_format=TrainingPlan,
    )

    plan = response.output_parsed

    if plan is None:
        raise RuntimeError(
            "OpenAI returned no structured "
            "training plan"
        )

    if (
        plan.year != target_year
        or plan.month != target_month
    ):
        raise RuntimeError(
            "OpenAI returned a plan for the "
            "wrong month"
        )

    target_prefix = (
        f"{target_year:04d}-"
        f"{target_month:02d}-"
    )

    unavailable_dates = set(
        context[
            "planning_constraints"
        ][
            "unavailable_dates"
        ]
    )

    workout_dates = set()

    for workout in plan.workouts:
        if not workout.date.startswith(
            target_prefix
        ):
            raise RuntimeError(
                "OpenAI returned a workout "
                "outside the target month"
            )

        if workout.date in unavailable_dates:
            raise RuntimeError(
                "OpenAI scheduled a workout "
                "on an unavailable date: "
                f"{workout.date}"
            )

        if workout.date in workout_dates:
            raise RuntimeError(
                "OpenAI scheduled multiple "
                "workouts on the same date: "
                f"{workout.date}"
            )

        workout_dates.add(
            workout.date
        )

    draft = {
        "status": "draft",
        "generated_at": now.isoformat(),
        "target_month": (
            f"{target_year:04d}-"
            f"{target_month:02d}"
        ),
        "sessions_per_week":
            sessions_per_week,
        "model": MODEL,
        "prompt_version":
            PROMPT_VERSION,
        "input_fingerprint":
            fingerprint,
        "planning_context":
            context,
        "workouts": [
            workout.model_dump()
            for workout in plan.workouts
        ],
    }

    DRAFT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = DRAFT_DIR / (
        f"{target_year:04d}-"
        f"{target_month:02d}.json"
    )

    temp_file = output_file.with_suffix(
        ".json.tmp"
    )

    temp_file.write_text(
        json.dumps(
            draft,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_file.chmod(0o600)
    temp_file.replace(output_file)
    output_file.chmod(0o600)

    return MonthlyPlanResult(
        path=str(output_file),
        cache_hit=False,
        openai_calls=1,
        input_fingerprint=fingerprint,
    )

    if __name__ == "__main__":
        result = generate_monthly_plan()

        print(
            "Training plan draft:",
            result.path,
        )
        print(
            "Cache:",
            "HIT" if result.cache_hit else "MISS",
        )
        print(
            "OpenAI calls:",
            result.openai_calls,
        )