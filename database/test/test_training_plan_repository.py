from datetime import date

from database.engine import SessionLocal
from database.repositories.training_plan_repository import (
    TrainingPlanRepository,
)


session = SessionLocal()

try:
    repository = TrainingPlanRepository(
        session
    )

    plan = repository.create_plan(
        year=2099,
        month=1,
        sessions_per_week=3,
        status="draft",
        source="test",
    )

    repository.add_workout(
        plan,
        scheduled_date=date(
            2099,
            1,
            3,
        ),
        name="Repository Test",
        description="Test",
        status="planned",
        warmup="5m",
        repeat=1,
        work="30m,100-110w,16-18spm",
        recovery=None,
        cooldown="5m",
    )

    loaded = repository.get_plan(
        2099,
        1,
    )

    assert loaded is not None
    assert loaded.year == 2099
    assert loaded.month == 1
    assert len(loaded.workouts) == 1

    workout = loaded.workouts[0]

    assert workout.name == "Repository Test"
    assert workout.status == "planned"

    print("TrainingPlanRepository OK")

finally:
    # Testdaten niemals persistieren.
    session.rollback()
    session.close()