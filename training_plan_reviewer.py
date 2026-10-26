import json
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

from availability_context import (
    build_availability_context,
)
from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)
from endurain_client import EndurainClient
from training_context import build_training_context


DRAFT_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)

REVIEW_DIR = Path(
    "/var/lib/pirowflo-control/training-reviews"
)

MODEL = "gpt-6-luna"


class TrainingPlanChange(BaseModel):
    action: str
    original_date: str
    new_date: str | None = None
    reason: str
    name: str | None = None
    description: str | None = None
    warmup: str | None = None
    repeat: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )
    work: str | None = None
    recovery: str | None = None
    cooldown: str | None = None


class TrainingPlanReview(BaseModel):
    plan_still_suitable: bool
    summary: str
    changes: list[TrainingPlanChange]

def _write_review(
    target_month: str,
    review: TrainingPlanReview,
    now: datetime,
) -> Path:
    REVIEW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        REVIEW_DIR /
        f"{target_month}.json"
    )

    data = {
        "status": "pending",
        "target_month": target_month,
        "generated_at": now.isoformat(),
        "review": review.model_dump(),
    }

    temp_file = output_file.with_suffix(
        ".json.tmp"
    )

    temp_file.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_file.chmod(0o600)
    temp_file.replace(output_file)
    output_file.chmod(0o600)

    return output_file

def review_training_plan(
    target_month: str,
    now: datetime | None = None,
) -> TrainingPlanReview:
    if now is None:
        now = datetime.now()

    draft_file = (
        DRAFT_DIR /
        f"{target_month}.json"
    )

    if not draft_file.exists():
        raise RuntimeError(
            f"No training plan for {target_month}"
        )

    plan = json.loads(
        draft_file.read_text(
            encoding="utf-8",
        )
    )

    year, month = map(
        int,
        target_month.split("-"),
    )

    start = datetime(
        year,
        month,
        1,
    )

    if month == 12:
        end = datetime(
            year + 1,
            1,
            1,
        )
    else:
        end = datetime(
            year,
            month + 1,
            1,
        )

    calendar = NextcloudCalendarClient(
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

    events = calendar.get_events_for_range(
        start,
        end,
    )

    availability = build_availability_context(
        events
    )

    history_start = datetime(
        now.year,
        now.month,
        1,
    )

    history_end = now

    if now.month == 12:
        training_calendar_end = datetime(
            now.year + 1,
            1,
            1,
        )
    else:
        training_calendar_end = datetime(
            now.year,
            now.month + 1,
            1,
        )

    endurain = EndurainClient(
        server=os.environ["ENDURAIN_SERVER"],
        username=os.environ["ENDURAIN_USERNAME"],
        password=os.environ["ENDURAIN_PASSWORD"],
    )

    training_calendar = NextcloudCalendarClient(
        calendar_url=os.environ[
            "NEXTCLOUD_CALENDAR_URL"
        ],
        username=os.environ[
            "NEXTCLOUD_USERNAME"
        ],
        app_password=os.environ[
            "NEXTCLOUD_APP_PASSWORD"
        ],
    )

    activities = (
        endurain.get_rowing_activities_for_range(
            history_start,
            history_end,
        )
    )

    training_events = (
        training_calendar.get_events_for_range(
            history_start,
            training_calendar_end,
        )
    )

    training_context = build_training_context(
        events=training_events,
        activities=activities,
        now=now,
    )

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
    )

    response = client.responses.parse(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """
Du überprüfst einen bestehenden Trainingsplan für
Indoor-Rudern.

Der Plan wurde bereits erstellt und soll möglichst
stabil bleiben.

Ändere nur Trainingseinheiten, wenn dafür ein
konkreter Grund besteht.

Mögliche Aktionen:

- keep:
  Training unverändert lassen.

- move:
  Training auf einen anderen Tag verschieben.

- skip:
  Training bewusst aussetzen. Der Termin bleibt als
  geplante Einheit erhalten, wird aber als ausgesetzt
  markiert und soll nicht als versäumtes Training
  bewertet werden.

- modify:
  Trainingsinhalt oder Belastung verändern.

Wichtig:

Abwesenheitszeiträume mit unavailable_periods
bedeuten, dass dort KEIN Training stattfinden kann.

TRAINING_CONTEXT enthält die tatsächliche
Trainingsentwicklung des laufenden Monats bis zum
Zeitpunkt der Überprüfung.

- status=linked:
  Geplantes Training und Endurain-Aktivität wurden
  bestätigt miteinander verknüpft.

- status=unlinked:
  Ein Training war geplant, besitzt aber keine
  bestätigte Endurain-Zuordnung.

- status=future:
  Das Training liegt noch in der Zukunft und darf
  NICHT als ausgelassen bewertet werden.

- free_activities:
  Tatsächlich absolvierte Ruderaktivitäten ohne
  bestätigte Zuordnung zu einem geplanten Training.

Die durchschnittliche Leistung einer Endurain-
Aktivität umfasst Warm-up, Hauptteil, Erholungen und
Cool-down. Vergleiche sie daher nicht direkt mit dem
Wattziel des Hauptteils.

Berücksichtige die tatsächliche Trainingsentwicklung
bei der Entscheidung, ob zukünftige Einheiten
unverändert bleiben oder angepasst werden sollten.

Bereits absolvierte Trainings dürfen niemals
nachträglich geändert, verschoben oder ausgesetzt
werden.

Versuche nicht, wegen einer Abwesenheit sämtliche
ausgefallenen Einheiten unmittelbar davor oder danach
nachzuholen.

Eine Trainingspause darf bewusst eine
Regenerationsphase sein.

Zwischen intensiven Trainingseinheiten muss
ausreichende Regeneration liegen.

Grundlagentraining soll weiterhin den größten Anteil
ausmachen.

Bei action=move muss new_date gesetzt sein.

Bei action=modify müssen die neuen Trainingsparameter
angegeben werden.

Bei action=keep oder action=skip ist new_date nicht
erforderlich.

Gib nur Änderungen zurück, die tatsächlich relevant
sind. Einheiten, die unverändert bleiben können,
müssen NICHT einzeln als keep aufgeführt werden.
""",
            },
            {
                "role": "user",
                "content": (
                    f"Überprüfe diesen Trainingsplan mit Stand "
                    f"{now.date().isoformat()}.\n\n"
                    "TRAININGSPLAN:\n"
                    + json.dumps(
                        plan["workouts"],
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n\nVERFÜGBARKEIT:\n"
                    + json.dumps(
                        availability,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n\nTRAININGSENTWICKLUNG:\n"
                    + json.dumps(
                        training_context,
                        ensure_ascii=False,
                        indent=2,
                    )
                ),
            },
        ],
        text_format=TrainingPlanReview,
    )

    review = response.output_parsed

    if review is None:
        raise RuntimeError(
            "OpenAI returned no structured review"
        )

    today = now.date()

    for change in review.changes:
        try:
            original_date = datetime.fromisoformat(
                change.original_date
            ).date()
        except ValueError as exc:
            raise RuntimeError(
                "OpenAI returned an invalid original_date: "
                f"{change.original_date}"
            ) from exc

        if original_date <= today:
            raise RuntimeError(
                "OpenAI attempted to change a training "
                "that is not in the future: "
                f"{change.original_date}"
            )

        if change.action not in {
            "move",
            "skip",
            "modify",
        }:
            raise RuntimeError(
                "OpenAI returned an unsupported action: "
                f"{change.action}"
            )

        if change.action == "move":
            if change.new_date is None:
                raise RuntimeError(
                    "Move action has no new_date"
                )

            try:
                new_date = datetime.fromisoformat(
                    change.new_date
                ).date()
            except ValueError as exc:
                raise RuntimeError(
                    "OpenAI returned an invalid new_date: "
                    f"{change.new_date}"
                ) from exc

            if new_date <= today:
                raise RuntimeError(
                    "OpenAI attempted to move a training "
                    "to a date that is not in the future: "
                    f"{change.new_date}"
                )

    if review.changes:    
        _write_review(
            target_month,
            review,
            now,
        )

    return review
