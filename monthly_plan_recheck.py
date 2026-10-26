import json
from datetime import date

from sqlalchemy import select

from database.engine import SessionLocal
from database.models import (
    MonthlyReview,
    TrainingPlan,
)
from database.models import (
    CoachRecommendation,
    MonthlyReview,
    TrainingPlan,
)


def _previous_month(
    year: int,
    month: int,
) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12

    return year, month - 1


def check_plan_reassessment_needed(
    *,
    target_year: int,
    target_month: int,
) -> dict:
    source_year, source_month = (
        _previous_month(
            target_year,
            target_month,
        )
    )

    with SessionLocal() as session:
        plan = session.scalar(
            select(TrainingPlan)
            .where(
                TrainingPlan.year
                == target_year,
                TrainingPlan.month
                == target_month,
            )
        )

        if plan is None:
            return {
                "needed": False,
                "reason":
                    "target_plan_missing",
                "target_month":
                    f"{target_year}-"
                    f"{target_month:02d}",
            }

        review = session.scalar(
            select(MonthlyReview)
            .where(
                MonthlyReview.year
                == source_year,
                MonthlyReview.month
                == source_month,
                MonthlyReview.input_fingerprint
                != "",
            )
            .order_by(
                MonthlyReview.created_at.desc()
            )
        )

        if review is None:
            return {
                "needed": False,
                "reason":
                    "monthly_review_missing",
                "target_month":
                    f"{target_year}-"
                    f"{target_month:02d}",
            }

        details = json.loads(
            review.review_json
        )

        signals = []

        if review.assessment == "concerning":
            signals.append(
                "monthly_assessment_concerning"
            )

        if review.trend == "declining":
            signals.append(
                "monthly_trend_declining"
            )

        if (
            review.load_assessment
            in {"high", "low"}
        ):
            signals.append(
                "monthly_load_not_appropriate"
            )

        if (
            review.recovery_assessment
            in {"concerning"}
        ):
            signals.append(
                "monthly_recovery_concerning"
            )

        if (
            details.get("progression")
            == "concerning"
        ):
            signals.append(
                "monthly_progression_concerning"
            )

        return {
            "needed": bool(signals),
            "reason": (
                "reassessment_signals"
                if signals
                else "plan_can_continue"
            ),
            "source_month":
                f"{source_year}-"
                f"{source_month:02d}",
            "target_month":
                f"{target_year}-"
                f"{target_month:02d}",
            "training_plan_id":
                plan.id,
            "monthly_review_id":
                review.id,
            "signals":
                signals,
        }
        
def create_plan_reassessment_recommendation(
    *,
    target_year: int,
    target_month: int,
) -> dict:
    result = check_plan_reassessment_needed(
        target_year=target_year,
        target_month=target_month,
    )

    if not result["needed"]:
        return {
            **result,
            "recommendation_created": False,
            "recommendation_id": None,
        }

    plan_id = result[
        "training_plan_id"
    ]

    review_id = result[
        "monthly_review_id"
    ]

    with SessionLocal() as session:
        existing_rows = session.scalars(
            select(CoachRecommendation)
            .where(
                CoachRecommendation.type
                == "monthly_plan_reassessment",
                CoachRecommendation.status
                == "pending",
                CoachRecommendation.training_plan_id
                == plan_id,
            )
            .order_by(
                CoachRecommendation.created_at.desc()
            )
        ).all()

        # Nicht bei jedem Timer-Lauf dieselbe
        # Recommendation erneut erzeugen.
        for existing in existing_rows:
            try:
                payload = json.loads(
                    existing.payload_json
                )
            except json.JSONDecodeError:
                continue

            if (
                payload.get(
                    "monthly_review_id"
                )
                == review_id
            ):
                return {
                    **result,
                    "recommendation_created": False,
                    "recommendation_id":
                        existing.id,
                }

        payload = {
            "source_month":
                result["source_month"],
            "target_month":
                result["target_month"],
            "monthly_review_id":
                review_id,
            "training_plan_id":
                plan_id,
            "signals":
                result.get(
                    "signals",
                    [],
                ),
        }

        recommendation = (
            CoachRecommendation(
                type=(
                    "monthly_plan_reassessment"
                ),
                status="pending",
                action="review_training_plan",
                training_plan_id=plan_id,
                reason=(
                    "Der Monatsabschluss enthält "
                    "deutliche Signale, die eine "
                    "Überprüfung des bestehenden "
                    "Trainingsplans sinnvoll machen."
                ),
                payload_json=json.dumps(
                    payload,
                    ensure_ascii=False,
                ),
            )
        )

        session.add(recommendation)
        session.commit()
        session.refresh(recommendation)

        return {
            **result,
            "recommendation_created": True,
            "recommendation_id":
                recommendation.id,
        }