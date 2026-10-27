from database.models import Workout


def phase_duration_seconds(
    definition: str | None,
) -> int:
    if not definition:
        return 0

    duration = definition.split(
        ",",
        1,
    )[0].strip().lower()

    if duration.endswith("m"):
        return int(duration[:-1]) * 60

    if duration.endswith("s"):
        return int(duration[:-1])

    raise ValueError(
        f"Unsupported duration: {duration}"
    )


def planned_duration_seconds(
    workout: Workout,
) -> int:
    repeat = max(
        workout.repeat or 1,
        1,
    )

    warmup = phase_duration_seconds(
        workout.warmup
    )

    work = phase_duration_seconds(
        workout.work
    )

    recovery = phase_duration_seconds(
        workout.recovery
    )

    cooldown = phase_duration_seconds(
        workout.cooldown
    )

    return (
        warmup
        + repeat * work
        + repeat * recovery
        + cooldown
    )