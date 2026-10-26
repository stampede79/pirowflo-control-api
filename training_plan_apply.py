import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from nextcloud_calendar_client import NextcloudCalendarClient
from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    CalendarSync,
    TrainingPlan as TrainingPlanModel,
    Workout,
)
from monthly_planning_context import (
    build_monthly_planning_input,
)
from monthly_training_planner import (
    _input_fingerprint,
)



DRAFT_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)

def _validate_draft_fingerprint(
    draft: dict[str, Any],
) -> None:
    target_month = draft.get(
        "target_month"
    )

    stored_fingerprint = draft.get(
        "input_fingerprint"
    )

    if not target_month:
        raise RuntimeError(
            "Draft has no target_month"
        )

    if not stored_fingerprint:
        raise RuntimeError(
            "Draft has no input_fingerprint"
        )

    year, month = map(
        int,
        target_month.split("-"),
    )

    current_context = (
        build_monthly_planning_input(
            target_year=year,
            target_month=month,
        )
    )

    current_fingerprint = (
        _input_fingerprint(
            current_context
        )
    )

    if (
        current_fingerprint
        != stored_fingerprint
    ):
        raise RuntimeError(
            "Training plan draft is stale. "
            "Planning context has changed."
        )

def _get_calendar_events(
    client: NextcloudCalendarClient,
    target_month: str,
) -> dict[str, dict[str, Any]]:
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

    events = client.get_events_for_range(
        start,
        end,
    )

    return {
        event["uid"]: event
        for event in events
        if event.get("uid")
    }

def _persist_training_plan(
    *,
    draft: dict[str, Any],
    calendar_events: dict[
        str,
        dict[str, Any],
    ],
) -> int:
    target_month = draft["target_month"]

    year, month = map(
        int,
        target_month.split("-"),
    )

    with SessionLocal() as session:
        existing = session.scalar(
            select(TrainingPlanModel)
            .where(
                TrainingPlanModel.year == year,
                TrainingPlanModel.month == month,
            )
        )

        if existing is not None:
            raise RuntimeError(
                "Training plan already exists "
                f"for {target_month}"
            )

        now = datetime.now()

        plan = TrainingPlanModel(
            year=year,
            month=month,
            status="active",
            sessions_per_week=draft.get(
                "sessions_per_week"
            ),
            source="ai",
            approved_at=now,
        )

        session.add(plan)
        session.flush()

        for item in draft["workouts"]:
            workout = Workout(
                training_plan_id=plan.id,
                scheduled_date=(
                    datetime.fromisoformat(
                        item["date"]
                    ).date()
                ),
                name=item["name"],
                description=item.get(
                    "description",
                    "",
                ),
                status="planned",
                warmup=item.get("warmup"),
                repeat=item.get(
                    "repeat",
                    1,
                ),
                work=item["work"],
                recovery=item.get(
                    "recovery"
                ),
                cooldown=item.get(
                    "cooldown"
                ),
            )

            session.add(workout)
            session.flush()

            uid = (
                "pirowflo-plan-"
                f"{target_month}-"
                f'{item["date"]}'
                "@pirowflo"
            )

            event = calendar_events.get(
                uid
            )

            if event is None:
                session.rollback()

                raise RuntimeError(
                    "Created calendar event "
                    "could not be found: "
                    f"{uid}"
                )

            session.add(
                CalendarSync(
                    workout_id=workout.id,
                    calendar_uid=uid,
                    calendar_href=event.get(
                        "href"
                    ),
                    calendar_etag=event.get(
                        "etag"
                    ),
                    sync_status="synced",
                    last_synced_at=now,
                )
            )

        session.commit()

        return plan.id

def _build_description(
    workout: dict[str, Any],
    draft: dict[str, Any],
) -> str:
    lines = [
        workout["description"].strip(),
        "",
        "[PIROWFLO]",
    ]

    warmup = workout.get("warmup")

    if warmup:
        lines.append(f"warmup={warmup}")

    repeat = workout.get("repeat", 1)

    if repeat > 1:
        lines.append(f"repeat={repeat}")

    lines.append(
        f'work={workout["work"]}'
    )

    recovery = workout.get("recovery")

    if recovery:
        lines.append(
            f"recovery={recovery}"
        )

    cooldown = workout.get("cooldown")

    if cooldown:
        lines.append(
            f"cooldown={cooldown}"
        )

    lines.extend(
        [
            "[/PIROWFLO]",
            "",
            "[PIROWFLO_PLAN]",
            (
                "target_month="
                f'{draft["target_month"]}'
            ),
            (
                "generated_at="
                f'{draft["generated_at"]}'
            ),
            "[/PIROWFLO_PLAN]",
        ]
    )

    return "\n".join(lines)


def preview_training_plan(
    target_month: str,
) -> list[dict[str, Any]]:
    draft_file = (
        DRAFT_DIR /
        f"{target_month}.json"
    )

    if not draft_file.exists():
        raise RuntimeError(
            f"No training plan draft for "
            f"{target_month}"
        )

    draft = json.loads(
        draft_file.read_text(
            encoding="utf-8",
        )
    )

    if draft.get("target_month") != target_month:
        raise RuntimeError(
            "Draft target month does not match "
            "requested target month"
        )

    applied_event_uids = set(
        draft.get(
            "applied_event_uids",
            [],
        )
    )

    result: list[dict[str, Any]] = []

    for workout in draft["workouts"]:
        date = workout["date"]

        if not date.startswith(
            f"{target_month}-"
        ):
            raise RuntimeError(
                "Workout outside target month: "
                f"{date}"
            )

        uid = (
            "pirowflo-plan-"
            f"{target_month}-"
            f"{date}"
            "@pirowflo"
        )

        result.append(
            {
                "date": date,
                "name": workout["name"],
                "uid": uid,
                "already_applied":
                    uid in applied_event_uids,
                "description":
                    _build_description(
                        workout,
                        draft,
                    ),
            }
        )

    return result

def find_calendar_conflicts(
    target_month: str,
) -> list[dict[str, Any]]:
    preview = preview_training_plan(
        target_month
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

    client = NextcloudCalendarClient(
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

    events = client.get_events_for_range(
        start,
        end,
    )

    pirowflo_events = [
        event
        for event in events
        if "[PIROWFLO]" in event["description"]
    ]

    conflicts: list[dict[str, Any]] = []

    for workout in preview:
        workout_date = workout["date"]

        for event in pirowflo_events:
            if (
                event["start"].date().isoformat()
                != workout_date
            ):
                continue

            # Derselbe bereits vom Planner erzeugte
            # Termin ist kein Konflikt.
            if event.get("uid") == workout["uid"]:
                continue

            conflicts.append(
                {
                    "date": workout_date,
                    "planned_name":
                        workout["name"],
                    "existing_name":
                        event["summary"],
                    "existing_uid":
                        event.get("uid"),
                }
            )

    return conflicts

def apply_training_plan(
    target_month: str,
) -> dict[str, Any]:
    draft_file = (
        DRAFT_DIR /
        f"{target_month}.json"
    )

    if not draft_file.exists():
        raise RuntimeError(
            f"No training plan draft for "
            f"{target_month}"
        )

    draft = json.loads(
        draft_file.read_text(
            encoding="utf-8",
        )
    )

    status = draft.get("status")

    if status == "applied":
        return draft

    if status != "draft":
        raise RuntimeError(
            f"Cannot apply training plan "
            f"with status {status!r}"
        )

    if draft.get("target_month") != target_month:
        raise RuntimeError(
            "Draft target month does not match "
            "requested target month"
        )

    _validate_draft_fingerprint(
        draft
    )

    year, month = map(
        int,
        target_month.split("-"),
    )

    with SessionLocal() as session:
        existing_plan = session.scalar(
            select(TrainingPlanModel)
            .where(
                TrainingPlanModel.year == year,
                TrainingPlanModel.month == month,
            )
        )

        if existing_plan is not None:
            raise RuntimeError(
                "Training plan already exists "
                f"for {target_month}"
            )

    client = NextcloudCalendarClient(
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

    applied_event_uids = set(
        draft.get(
            "applied_event_uids",
            [],
        )
    )

    conflicts = find_calendar_conflicts(
        target_month
    )

    if conflicts:
        raise RuntimeError(
            f"Training plan has "
            f"{len(conflicts)} calendar conflict(s)"
        )

    for workout in draft["workouts"]:
        date = datetime.fromisoformat(
            workout["date"]
        )

        expected_prefix = (
            f"{target_month}-"
        )

        if not workout["date"].startswith(
            expected_prefix
        ):
            raise RuntimeError(
                "Workout outside target month: "
                f'{workout["date"]}'
            )

        uid = (
            "pirowflo-plan-"
            f"{target_month}-"
            f'{workout["date"]}'
            "@pirowflo"
        )

        if uid in applied_event_uids:
            continue

        description = _build_description(
            workout,
            draft,
        )

        client.create_event(
            date=date,
            summary=workout["name"],
            description=description,
            uid=uid,
        )

        applied_event_uids.add(uid)

        # Fortschritt nach JEDEM erfolgreich
        # erstellten Termin persistieren.
        draft["applied_event_uids"] = sorted(
            applied_event_uids
        )

        _write_draft(
            draft_file,
            draft,
        )

        calendar_events = _get_calendar_events(
        client,
        target_month,
    )

    plan_id = _persist_training_plan(
        draft=draft,
        calendar_events=calendar_events,
    )

    draft["status"] = "applied"
    draft["applied_at"] = (
        datetime.now().isoformat()
    )
    draft["training_plan_id"] = plan_id

    draft["applied_event_uids"] = sorted(
        applied_event_uids
    )

    _write_draft(
        draft_file,
        draft,
    )

    return draft


def _write_draft(
    draft_file: Path,
    draft: dict[str, Any],
) -> None:
    temp_file = draft_file.with_suffix(
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
    temp_file.replace(draft_file)
    draft_file.chmod(0o600)
