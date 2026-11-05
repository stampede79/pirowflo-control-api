from monthly_planning_context import (
    _actual_training_load,
)


def test_actual_training_load_includes_free_activities():
    workout_items = [
        {
            "status": "completed",
            "actual": {
                "duration_minutes": 45.0,
                "distance_km": 8.8,
            },
        },
        {
            "status": "completed",
            "actual": {
                "duration_minutes": 33.2,
                "distance_km": 6.66,
            },
        },
        {
            "status": "planned",
            "actual": None,
        },
    ]

    free_activity_items = [
        {
            "duration_minutes": 18.8,
            "distance_km": 3.66,
            "analysis": {
                "load_assessment": "low",
                "effort": "easy",
            },
        },
    ]

    result = _actual_training_load(
        workout_items,
        free_activity_items,
    )

    assert result == {
        "completed_planned_sessions": 2,
        "free_sessions": 1,
        "total_sessions": 3,
        "planned_duration_minutes": 78.2,
        "free_duration_minutes": 18.8,
        "total_duration_minutes": 97.0,
        "planned_distance_km": 15.46,
        "free_distance_km": 3.66,
        "total_distance_km": 19.12,
    }

def test_actual_training_load_does_not_count_open_workouts():
    workout_items = [
        {
            "status": "planned",
            "actual": None,
        },
        {
            "status": "missed",
            "actual": None,
        },
    ]

    result = _actual_training_load(
        workout_items,
        [],
    )

    assert result == {
        "completed_planned_sessions": 0,
        "free_sessions": 0,
        "total_sessions": 0,
        "planned_duration_minutes": 0,
        "free_duration_minutes": 0,
        "total_duration_minutes": 0,
        "planned_distance_km": 0,
        "free_distance_km": 0,
        "total_distance_km": 0,
    }