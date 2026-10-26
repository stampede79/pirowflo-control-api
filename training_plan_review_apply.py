import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from nextcloud_calendar_client import (
    NextcloudCalendarClient,
)


REVIEW_DIR = Path(
    "/var/lib/pirowflo-control/training-reviews"
)


def _set_plan_status(
    description: str,
    *,
    status: str,
    reason: str,
) -> str:
    start_marker = "[PIROWFLO_PLAN_STATUS]"
    end_marker = "[/PIROWFLO_PLAN_STATUS]"

    block = (
        f"{start_marker}\n"
        f"status={status}\n"
        f"reason={reason}\n"
        f"{end_marker}"
    )

    start = description.find(start_marker)
    end = description.find(end_marker)

    if start != -1 and end != -1:
        end += len(end_marker)

        return (
            description[:start].rstrip()
            + "\n\n"
            + block
            + description[end:]
        ).strip()

    return (
        description.rstrip()
        + "\n\n"
        + block
    ).strip()


def _write_review(
    review_file: Path,
    data: dict[str, Any],
) -> None:
    temp_file = review_file.with_suffix(
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
    temp_file.replace(review_file)
    review_file.chmod(0o600)


def apply_training_plan_review(
    target_month: str,
) -> dict[str, Any]:
    review_file = (
        REVIEW_DIR /
        f"{target_month}.json"
    )

    if not review_file.exists():
        raise RuntimeError(
            f"No training plan review for "
            f"{target_month}"
        )

    data = json.loads(
        review_file.read_text(
            encoding="utf-8",
        )
    )

    if data.get("status") == "applied":
        return data

    if data.get("status") != "pending":
        raise RuntimeError(
            "Training plan review is not pending"
        )

    if data.get("target_month") != target_month:
        raise RuntimeError(
            "Review target month does not match"
        )

    review = data.get("review")

    if not isinstance(review, dict):
        raise RuntimeError(
            "Review payload is invalid"
        )

    changes = review.get("changes")

    if not isinstance(changes, list):
        raise RuntimeError(
            "Review changes are invalid"
        )

    # V1 unterstützt absichtlich nur skip.
    unsupported = [
        change
        for change in changes
        if change.get("action") != "skip"
    ]

    if unsupported:
        raise RuntimeError(
            "Review contains unsupported actions"
        )

    year, month = map(
        int,
        target_month.split("-"),
    )

    start = datetime(year, month, 1)

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

    events_by_uid = {
        event["uid"]: event
        for event in events
        if event.get("uid")
    }

    applied_changes = set(
        data.get(
            "applied_changes",
            [],
        )
    )

    # Zuerst ALLE Änderungen validieren.
    # Vorher wird kein Kalendertermin verändert.
    prepared: list[
        tuple[str, dict[str, Any], dict[str, Any]]
    ] = []

    for change in changes:
        original_date = change.get(
            "original_date"
        )

        if not isinstance(
            original_date,
            str,
        ):
            raise RuntimeError(
                "Review change has no valid "
                "original_date"
            )

        if not original_date.startswith(
            f"{target_month}-"
        ):
            raise RuntimeError(
                "Review change is outside "
                f"target month: {original_date}"
            )

        uid = (
            "pirowflo-plan-"
            f"{target_month}-"
            f"{original_date}"
            "@pirowflo"
        )

        if uid in applied_changes:
            continue

        event = events_by_uid.get(uid)

        if event is None:
            raise RuntimeError(
                "Planned calendar event not found: "
                f"{uid}"
            )

        reason = change.get("reason")

        if not isinstance(reason, str) or not reason:
            raise RuntimeError(
                "Skip change has no reason: "
                f"{original_date}"
            )

        prepared.append(
            (
                uid,
                event,
                change,
            )
        )

    # Erst nach vollständiger Validierung schreiben.
    for uid, event, change in prepared:
        new_description = _set_plan_status(
            event["description"],
            status="skipped",
            reason=change["reason"],
        )

        client.update_event_description(
            event,
            new_description,
        )

        applied_changes.add(uid)

        # Nach jedem erfolgreichen Update speichern,
        # damit ein Teilfehler wiederaufnehmbar ist.
        data["applied_changes"] = sorted(
            applied_changes
        )

        _write_review(
            review_file,
            data,
        )

    data["status"] = "applied"
    data["applied_at"] = (
        datetime.now().isoformat()
    )
    data["applied_changes"] = sorted(
        applied_changes
    )

    _write_review(
        review_file,
        data,
    )

    return data