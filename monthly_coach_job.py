import argparse
from datetime import date, timedelta

from monthly_review_generator import (
    _month_range,
    _week_keys_for_month,
    build_monthly_review_input,
    generate_monthly_review,
)
from monthly_training_planner import (
    generate_monthly_plan,
)
from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    TrainingPlan,
)
from monthly_plan_recheck import (
    check_plan_reassessment_needed,
    create_plan_reassessment_recommendation,
)


from weekly_review_generator import (
    generate_weekly_review,
)

def next_month_from_year_month(
    year: int,
    month: int,
) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1

    return year, month + 1

def previous_month(
    today: date,
) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12

    return today.year, today.month - 1


def next_month_from_date(
    today: date,
) -> tuple[int, int]:
    if today.month == 12:
        return today.year + 1, 1

    return today.year, today.month + 1

def ensure_completed_weekly_reviews(
    *,
    year: int,
    month: int,
    today: date,
) -> bool:
    start, end = _month_range(
        year,
        month,
    )

    if not monthly_weekly_reviews_ready(
        year=year,
        month=month,
        today=today,
    ):
        return False

    week_keys = sorted(
        _week_keys_for_month(
            start,
            end,
        )
    )

    for week_year, iso_week in week_keys:
        monday = date.fromisocalendar(
            week_year,
            iso_week,
            1,
        )

        week_end = (
            monday
            + timedelta(days=7)
        )

        if today < week_end:
            print(
                "Woche noch nicht abgeschlossen:",
                f"{week_year}-W{iso_week:02d}",
            )

            return False

        print(
            "Weekly Review sicherstellen:",
            f"{week_year}-W{iso_week:02d}",
        )

        generate_weekly_review(
            week_year,
            iso_week,
        )

    return True

def finalize_previous_month(
    *,
    year: int,
    month: int,
) -> int:
    print()
    print("Finalize previous month")
    print("=" * 72)
    print(
        "Monat:",
        f"{year}-{month:02d}",
    )

    input_data = build_monthly_review_input(
        year,
        month,
    )

    metrics = input_data[
        "summary_metrics"
    ]

    completed = metrics[
        "completed_workouts"
    ]

    open_workouts = metrics[
        "open_workouts"
    ]

    if completed == 0:
        print(
            "Keine abgeschlossenen Trainings."
        )
        print("OpenAI calls: 0")
        return 0

    if open_workouts > 0:
        print(
            f"Noch {open_workouts} "
            "Training(s) offen."
        )
        print(
            "Monatsabschluss wird "
            "übersprungen."
        )
        print("OpenAI calls: 0")
        return 0
    
    weekly_ready = (
        ensure_completed_weekly_reviews(
            year=year,
            month=month,
            today=date.today(),
        )
    )

    if not weekly_ready:
        print(
            "Mindestens eine relevante Woche "
            "ist noch nicht abgeschlossen."
        )
        print(
            "Monatsabschluss wird "
            "übersprungen."
        )
        print("OpenAI calls: 0")

        return 0
        
    review = generate_monthly_review(
        year,
        month,
    )

    target_year, target_month = (
        next_month_from_year_month(
            year,
            month,
        )
    )

    recheck = (
        create_plan_reassessment_recommendation(
            target_year=target_year,
            target_month=target_month,
        )
    )

    print()
    print("Plan recheck")
    print("=" * 72)
    print(
        "Zielmonat:",
        recheck["target_month"],
    )
    print(
        "Benötigt:",
        "JA"
        if recheck["needed"]
        else "NEIN",
    )
    print(
        "Grund:",
        recheck["reason"],
    )

    signals = recheck.get(
        "signals",
        []
    )

    if signals:
        print(
            "Signale:",
            ", ".join(signals),
        )

    if recheck["needed"]:
        print(
            "Eine Neubewertung des bestehenden "
            "Trainingsplans ist sinnvoll."
        )
        print(
            "Automatische Planänderungen werden "
            "nicht vorgenommen."
        )
    else:
        print(
            "Bestehender Trainingsplan kann "
            "unverändert fortgeführt werden."
        )

    print()
    print("Monthly Review")
    print("ID:", review.id)
    print(
        "Assessment:",
        review.assessment,
    )
    print(
        "Fingerprint:",
        review.input_fingerprint,
    )

    print()
    print(
        "Monatsabschluss erfolgreich."
    )

    return 0

def monthly_weekly_reviews_ready(
    *,
    year: int,
    month: int,
    today: date,
) -> bool:
    start, end = _month_range(
        year,
        month,
    )

    for week_year, iso_week in sorted(
        _week_keys_for_month(
            start,
            end,
        )
    ):
        monday = date.fromisocalendar(
            week_year,
            iso_week,
            1,
        )

        week_end = (
            monday
            + timedelta(days=7)
        )

        if today < week_end:
            return False

    return True

def prepare_next_month(
    *,
    year: int,
    month: int,
) -> int:
    print()
    print("Prepare next month")
    print("=" * 72)
    print(
        "Zielmonat:",
        f"{year}-{month:02d}",
    )

    with SessionLocal() as session:
        existing_plan = session.scalar(
            select(TrainingPlan)
            .where(
                TrainingPlan.year == year,
                TrainingPlan.month == month,
            )
        )

    if existing_plan is not None:
        print()
        print(
            "Training plan already exists "
            f"for {year}-{month:02d}."
        )
        print(
            "Preparation skipped."
        )
        print("OpenAI calls: 0")

        return 0

    result = generate_monthly_plan(
        target_year=year,
        target_month=month,
    )

    print()
    print(
        "Plan-Draft:",
        result.path,
    )
    print(
        "Cache:",
        "HIT"
        if result.cache_hit
        else "MISS",
    )
    print(
        "OpenAI calls:",
        result.openai_calls,
    )

    print()
    print(
        "Vorplanung erfolgreich."
    )

    return 0

def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "mode",
        choices={
            "prepare-next-month",
            "finalize-previous-month",
        },
    )

    parser.add_argument(
        "--year",
        type=int,
    )

    parser.add_argument(
        "--month",
        type=int,
    )

    args = parser.parse_args()

    today = date.today()

    if args.mode == "finalize-previous-month":
        if (
            args.year is not None
            and args.month is not None
        ):
            year = args.year
            month = args.month
        else:
            year, month = previous_month(
                today
            )

        return finalize_previous_month(
            year=year,
            month=month,
        )

    if (
        args.year is not None
        and args.month is not None
    ):
        year = args.year
        month = args.month
    else:
        year, month = next_month_from_date(
            today
        )

    return prepare_next_month(
        year=year,
        month=month,
    )


if __name__ == "__main__":
    raise SystemExit(main())