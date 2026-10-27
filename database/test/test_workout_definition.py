from types import SimpleNamespace

from workout_definition import (
    phase_duration_seconds,
    planned_duration_seconds,
)


def test_phase_duration_minutes():
    assert (
        phase_duration_seconds(
            "3m,135-145w"
        )
        == 180
    )


def test_phase_duration_seconds():
    assert (
        phase_duration_seconds(
            "90s,100w"
        )
        == 90
    )


def test_interval_duration_includes_last_recovery():
    workout = SimpleNamespace(
        warmup="7m",
        repeat=6,
        work="3m,135-145w",
        recovery="2m,90-100w",
        cooldown="5m",
    )

    assert (
        planned_duration_seconds(workout)
        == 42 * 60
    )


def test_continuous_workout_duration():
    workout = SimpleNamespace(
        warmup="5m",
        repeat=1,
        work="40m,105-110w,16-18spm",
        recovery=None,
        cooldown="5m",
    )

    assert (
        planned_duration_seconds(workout)
        == 50 * 60
    )
