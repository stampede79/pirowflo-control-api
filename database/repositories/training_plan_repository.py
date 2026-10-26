from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from database.models import TrainingPlan, Workout


class TrainingPlanRepository:
    def __init__(
        self,
        session: Session,
    ):
        self.session = session

    def get_plan(
        self,
        year: int,
        month: int,
    ) -> TrainingPlan | None:
        statement = (
            select(TrainingPlan)
            .options(
                selectinload(
                    TrainingPlan.workouts
                )
            )
            .where(
                TrainingPlan.year == year,
                TrainingPlan.month == month,
            )
        )

        return self.session.scalar(
            statement
        )

    def create_plan(
        self,
        *,
        year: int,
        month: int,
        sessions_per_week: int | None,
        status: str = "draft",
        source: str = "ai",
    ) -> TrainingPlan:
        existing = self.get_plan(
            year,
            month,
        )

        if existing is not None:
            raise ValueError(
                f"Training plan already exists "
                f"for {year:04d}-{month:02d}"
            )

        plan = TrainingPlan(
            year=year,
            month=month,
            sessions_per_week=sessions_per_week,
            status=status,
            source=source,
        )

        self.session.add(plan)
        self.session.flush()

        return plan

    def add_workout(
        self,
        plan: TrainingPlan,
        *,
        scheduled_date: date,
        name: str,
        description: str,
        status: str,
        warmup: str | None,
        repeat: int,
        work: str,
        recovery: str | None,
        cooldown: str | None,
    ) -> Workout:
        workout = Workout(
            training_plan=plan,
            scheduled_date=scheduled_date,
            name=name,
            description=description,
            status=status,
            warmup=warmup,
            repeat=repeat,
            work=work,
            recovery=recovery,
            cooldown=cooldown,
        )

        self.session.add(workout)
        self.session.flush()

        return workout