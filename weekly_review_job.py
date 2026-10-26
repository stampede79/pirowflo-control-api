from datetime import date, timedelta

from weekly_review_generator import (
    build_weekly_review_input,
    generate_weekly_review,
)
import argparse


def completed_iso_week(
    today: date,
) -> tuple[int, int]:
    current_monday = today - timedelta(
        days=today.weekday()
    )

    previous_week = (
        current_monday
        - timedelta(days=1)
    )

    iso = previous_week.isocalendar()

    return iso.year, iso.week


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
    )

    parser.add_argument(
        "--week",
        type=int,
    )

    args = parser.parse_args()

    try:
        today = date.today()

        if (
            args.year is not None
            and args.week is not None
        ):
            year = args.year
            iso_week = args.week
        else:
            year, iso_week = (
                completed_iso_week(today)
            )

        print()
        print("PiRowFlo Weekly Coach")
        print("=" * 72)
        print(
            "Review:",
            f"{year}-W{iso_week:02d}",
        )

        input_data = build_weekly_review_input(
            year,
            iso_week,
        )

        completed = input_data[
            "summary_metrics"
        ]["completed_workouts"]

        if completed == 0:
            print()
            print(
                "Keine abgeschlossenen Trainings "
                "in dieser Woche."
            )
            print(
                "Weekly Review wird übersprungen."
            )
            print("OpenAI calls: 0")

            return 0

        review = generate_weekly_review(
            year,
            iso_week,
        )

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
        print("Weekly Review erfolgreich.")

        return 0

    except Exception as exc:
        print()
        print("=" * 72)
        print("Weekly Review fehlgeschlagen.")
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())