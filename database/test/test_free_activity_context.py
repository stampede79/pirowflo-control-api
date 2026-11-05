from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.engine import Base
from database.models import (
    Activity,
    TrainingPlan,
    Workout,
    WorkoutActivityLink,
    WorkoutAnalysis,
)
from free_activity_context import (
    get_free_activities,
    serialize_free_activity,
)


def create_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
    )

    Base.metadata.create_all(engine)

    return Session(engine)


def activity(
    *,
    endurain_id: int,
    start_time: datetime,
    duration_seconds: float = 1200,
    distance_meters: float = 4000,
) -> Activity:
    return Activity(
        endurain_activity_id=endurain_id,
        start_time=start_time,
        duration_seconds=duration_seconds,
        distance_meters=distance_meters,
        average_power=100,
        normalized_power=105,
        average_hr=130,
        max_hr=145,
        average_spm=17,
    )


def test_unlinked_activity_is_free():
    with create_session() as session:
        row = activity(
            endurain_id=1001,
            start_time=datetime(
                2026,
                11,
                3,
                10,
                0,
            ),
        )

        session.add(row)
        session.flush()

        result = get_free_activities(
            session,
            date(2026, 11, 3),
            date(2026, 11, 4),
        )

        assert result == [row]


def test_linked_activity_is_not_free():
    with create_session() as session:
        plan = TrainingPlan(
            year=2026,
            month=11,
            status="active",
            source="test",
        )

        workout = Workout(
            training_plan=plan,
            scheduled_date=date(
                2026,
                11,
                3,
            ),
            name="Test",
            description="Test",
            status="completed",
            warmup="5m",
            repeat=1,
            work="20m,100-110w",
            recovery=None,
            cooldown="5m",
        )

        row = activity(
            endurain_id=1002,
            start_time=datetime(
                2026,
                11,
                3,
                10,
                0,
            ),
        )

        session.add_all(
            [
                plan,
                workout,
                row,
            ]
        )
        session.flush()

        session.add(
            WorkoutActivityLink(
                workout_id=workout.id,
                activity_id=row.id,
                status="linked",
                match_score=1.0,
            )
        )

        session.flush()

        result = get_free_activities(
            session,
            date(2026, 11, 3),
            date(2026, 11, 4),
        )

        assert result == []


def test_activity_outside_range_is_not_free():
    with create_session() as session:
        row = activity(
            endurain_id=1003,
            start_time=datetime(
                2026,
                11,
                2,
                23,
                59,
            ),
        )

        session.add(row)
        session.flush()

        result = get_free_activities(
            session,
            date(2026, 11, 3),
            date(2026, 11, 4),
        )

        assert result == []


def test_free_activities_are_sorted_by_start_time():
    with create_session() as session:
        later = activity(
            endurain_id=1004,
            start_time=datetime(
                2026,
                11,
                3,
                18,
                0,
            ),
        )

        earlier = activity(
            endurain_id=1005,
            start_time=datetime(
                2026,
                11,
                3,
                8,
                0,
            ),
        )

        session.add_all(
            [
                later,
                earlier,
            ]
        )
        session.flush()

        result = get_free_activities(
            session,
            date(2026, 11, 3),
            date(2026, 11, 4),
        )

        assert result == [
            earlier,
            later,
        ]


def test_serialize_free_activity():
    row = activity(
        endurain_id=1131,
        start_time=datetime(
            2026,
            11,
            3,
            9,
            34,
            57,
        ),
        duration_seconds=1128,
        distance_meters=3663,
    )

    result = serialize_free_activity(
        row
    )

    assert result == {
        "date": "2026-11-03",
        "start_time":
            "2026-11-03T09:34:57",
        "endurain_activity_id": 1131,
        "duration_minutes": 18.8,
        "distance_km": 3.66,
        "average_power": 100,
        "normalized_power": 105,
        "average_hr": 130,
        "max_hr": 145,
        "average_spm": 17,
        "analysis": None,
    }

def test_serialize_free_activity_with_analysis():
    row = activity(
        endurain_id=1131,
        start_time=datetime(
            2026,
            11,
            3,
            9,
            34,
            57,
        ),
        duration_seconds=1128,
        distance_meters=3663,
    )

    analysis = WorkoutAnalysis(
        workout_id=None,
        activity_id=1,
        execution="unknown",
        load_assessment="low",
        effort="easy",
        progression="unknown",
        recovery_concern=False,
        summary="Lockere zusätzliche Einheit.",
        recommendation=(
            "Die nächste Einheit wie geplant "
            "absolvieren."
        ),
        analysis_json="{}",
        metrics_json="{}",
        model="gpt-6-luna",
        prompt_version="9",
    )

    result = serialize_free_activity(
        row,
        analysis,
    )

    assert result["analysis"] == {
        "execution": "unknown",
        "load_assessment": "low",
        "effort": "easy",
        "progression": "unknown",
        "recovery_concern": False,
        "summary":
            "Lockere zusätzliche Einheit.",
        "recommendation": (
            "Die nächste Einheit wie geplant "
            "absolvieren."
        ),
        "prompt_version": "9",
    }