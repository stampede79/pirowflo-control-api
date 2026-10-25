import calendar
import json
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

from endurain_client import EndurainClient
from nextcloud_calendar_client import NextcloudCalendarClient
from training_context import build_training_context


MODEL = "gpt-6-luna"

DRAFT_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)


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
    now: datetime | None = None,
    sessions_per_week: int = 3,
) -> Path:
    if now is None:
        now = datetime.now()

    source_year = now.year
    source_month = now.month

    target_year, target_month = next_month(
        source_year,
        source_month,
    )

    source_start = datetime(
        source_year,
        source_month,
        1,
    )

    if source_month == 12:
        source_end = datetime(
            source_year + 1,
            1,
            1,
        )
    else:
        source_end = datetime(
            source_year,
            source_month + 1,
            1,
        )

    endurain = EndurainClient(
        server=os.environ["ENDURAIN_SERVER"],
        username=os.environ["ENDURAIN_USERNAME"],
        password=os.environ["ENDURAIN_PASSWORD"],
    )

    nextcloud = NextcloudCalendarClient(
        calendar_url=os.environ[
            "NEXTCLOUD_CALENDAR_URL"
        ],
        username=os.environ["NEXTCLOUD_USERNAME"],
        app_password=os.environ[
            "NEXTCLOUD_APP_PASSWORD"
        ],
    )

    activities = (
        endurain.get_rowing_activities_for_range(
            source_start,
            source_end,
        )
    )

    events = nextcloud.get_events_for_range(
        source_start,
        source_end,
    )

    context = build_training_context(
        events=events,
        activities=activities,
        now=now,
    )

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
    )

    target_name = month_name(
        target_year,
        target_month,
    )

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": f"""
Du erstellst einen personalisierten Trainingsplan für Indoor-Rudern.

Der Nutzer trainiert mit PiRowFlo und SmartRow.

Du erhältst Trainingsdaten des laufenden Monats.

Bedeutung der Daten:

- status=linked:
  Geplantes Training und Endurain-Aktivität wurden vom Nutzer bestätigt
  miteinander verknüpft. Diese Daten sind besonders zuverlässig.

- status=unlinked:
  Ein PiRowFlo-Training existiert, aber es gibt keine bestätigte
  Zuordnung zu einer Endurain-Aktivität.

- status=future:
  Das Training liegt zum Zeitpunkt der Planung noch in der Zukunft.
  Es darf NICHT als ausgelassen oder nicht absolviert bewertet werden.

- free_activities:
  Tatsächlich absolvierte Ruderaktivitäten ohne bestätigte Zuordnung
  zu einem PiRowFlo-Termin.

Die durchschnittliche Leistung einer Endurain-Aktivität umfasst Warm-up,
Hauptteil, Erholungen und Cool-down. Vergleiche sie daher NICHT direkt
mit dem Wattziel des Hauptteils.

Berücksichtige zukünftige Trainingseinheiten am Ende des laufenden
Monats bei der Terminierung der ersten Einheiten des Folgemonats.
Behandle diese Einheiten nicht als bereits absolviert, plane aber
ausreichende Regeneration für den Fall, dass sie planmäßig stattfinden.

Plane konservativ und leite Belastung und Umfang aus den tatsächlichen
Trainingsdaten ab. Steigere Umfang oder Intensität nur moderat.

Grundlagentraining soll den größten Anteil ausmachen.

Plane die Belastung nicht monoton über den gesamten Monat.
Berücksichtige eine leichtere Phase oder Regenerationswoche, wenn dies
angesichts des Vormonats sinnvoll ist.

Verwende ausschließlich Watt und SPM als Trainingsziele.

PiRowFlo-Format:
- Dauer: 5m, 30m usw.
- Leistung: 100-110w
- Schlagzahl: 16-18spm
- Kombination: 40m,105-110w,16-18spm

Plane {sessions_per_week} Einheiten pro Woche.

Erstelle ausschließlich Trainingseinheiten für {target_name}.
""",
            },
            {
                "role": "user",
                "content": (
                    f"Erstelle anhand dieser Trainingsdaten einen "
                    f"personalisierten Trainingsplan für "
                    f"{target_name}.\n\n"
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
            "OpenAI returned no structured training plan"
        )

    if (
        plan.year != target_year
        or plan.month != target_month
    ):
        raise RuntimeError(
            "OpenAI returned a plan for the wrong month"
        )

    target_prefix = (
        f"{target_year:04d}-{target_month:02d}-"
    )

    for workout in plan.workouts:
        if not workout.date.startswith(target_prefix):
            raise RuntimeError(
                "OpenAI returned a workout outside "
                "the target month"
            )

    last_source_day = calendar.monthrange(
        source_year,
        source_month,
    )[1]

    draft = {
        "status": "draft",
        "generated_at": now.isoformat(),
        "source_period": {
            "start": source_start.date().isoformat(),
            "end": (
                f"{source_year:04d}-"
                f"{source_month:02d}-"
                f"{last_source_day:02d}"
            ),
        },
        "target_month": (
            f"{target_year:04d}-"
            f"{target_month:02d}"
        ),
        "sessions_per_week": sessions_per_week,
        "model": MODEL,
        "training_context": context,
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

    return output_file


if __name__ == "__main__":
    result = generate_monthly_plan()

    print(
        f"Training plan draft created: {result}"
    )
