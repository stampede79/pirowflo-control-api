import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from nextcloud_calendar_client import NextcloudCalendarClient



DRAFT_DIR = Path(
    "/var/lib/pirowflo-control/training-plans"
)


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

    draft["status"] = "applied"
    draft["applied_at"] = (
        datetime.now().isoformat()
    )

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
