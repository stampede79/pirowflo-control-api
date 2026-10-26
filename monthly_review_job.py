import argparse
from datetime import date

from monthly_review_generator import (
    build_monthly_review_input,
    generate_monthly_review,
)


def previous_month(
    today: date,
) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12

    return today.year, today.month - 1


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
    )

    parser.add_argument(
        "--month",
        type=int,
    )

    parser.add_argument(
        "--force",
        action="store_true",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Check monthly review readiness "
            "without calling OpenAI"
        ),
    )

    args = parser.parse_args()

    if (
        args.year is not None
        and args.month is not None
    ):
        year = args.year
        month = args.month
    else:
        year, month = previous_month(
            date.today()
        )

    print()
    print("PiRowFlo Monthly Coach")
    print("=" * 72)
    print(
        "Review:",
        f"{year}-{month:02d}",
    )

    input_data = build_monthly_review_input(
        year,
        month,
    )

import argparse
from datetime import date

from monthly_review_generator import (
    build_monthly_review_input,
    generate_monthly_review,
)


def previous_month(
    today: date,
) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12

    return today.year, today.month - 1


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
    )

    parser.add_argument(
        "--month",
        type=int,
    )

    parser.add_argument(
        "--force",
        action="store_true",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Check monthly review readiness "
            "without calling OpenAI"
        ),
    )

    args = parser.parse_args()

    if (
        args.year is not None
        and args.month is not None
    ):
        year = args.year
        month = args.month
    else:
        year, month = previous_month(
            date.today()
        )

    print()
    print("PiRowFlo Monthly Coach")
    print("=" * 72)
    print(
        "Review:",
        f"{year}-{month:02d}",
    )

    input_data = build_monthly_review_input(
        year,
        month,
    )

    metrics = input_data[
        "summary_metrics"
    ]

    workouts = input_data["workouts"]

    weekly_reviews = input_data[
        "weekly_reviews"
    ]

    analysis_count = sum(
        1
        for workout in workouts
        if workout.get("analysis") is not None
    )

    completed = metrics[
        "completed_workouts"
    ]

    open_workouts = metrics[
        "open_workouts"
    ]

    skipped = metrics[
        "skipped_workouts"
    ]

    if args.check:
        ready = (
            completed > 0
            and open_workouts == 0
        )

        print()
        print("Monthly Coach Check")
        print("=" * 72)
        print(
            "Workouts:",
            metrics["planned_workouts"],
        )
        print(
            "Completed:",
            completed,
        )
        print(
            "Skipped:",
            skipped,
        )
        print(
            "Open:",
            open_workouts,
        )
        print(
            "Workout analyses:",
            analysis_count,
        )
        print(
            "Weekly reviews:",
            len(weekly_reviews),
        )
        print(
            "Training time:",
            f"{metrics['total_duration_minutes']} min",
        )
        print(
            "Distance:",
            f"{metrics['total_distance_km']} km",
        )

        print()

        if ready:
            print("Review ready: YES")
        elif completed == 0:
            print("Review ready: NO")
            print(
                "Reason: no completed workouts"
            )
        else:
            print("Review ready: NO")
            print(
                "Reason:",
                f"{open_workouts} workout(s) "
                "still open",
            )

        print("OpenAI calls: 0")

        return 0

    if completed == 0:
        print()
        print(
            "Keine abgeschlossenen Trainings "
            "in diesem Monat."
        )
        print(
            "Monthly Review wird übersprungen."
        )
        print("OpenAI calls: 0")

        return 0

    if (
        open_workouts > 0
        and not args.force
    ):
        print()
        print(
            f"Noch {open_workouts} Training(s) "
            "offen."
        )
        print(
            "Monthly Review wird noch nicht "
            "erzeugt."
        )
        print("OpenAI calls: 0")

        return 0

    review = generate_monthly_review(
        year,
        month,
    )

    print()
    print("Review ID:", review.id)
    print(
        "Assessment:",
        review.assessment,
    )
    print(
        "Fingerprint:",
        review.input_fingerprint,
    )

    print()
    print("Monthly Review erfolgreich.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())