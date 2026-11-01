from datetime import (
    datetime,
    timedelta,
)

from workout_phase_analyzer import (
    _phase_metrics,
    _analyze_interval_recovery,
    _max_rolling_average,
    analyze_workout_phases,
)

START = datetime(
    2026,
    10,
    28,
    10,
    0,
)


def stream(values):
    return [
        {
            "time":
                START + timedelta(seconds=index),
            "value":
                value,
        }
        for index, value in enumerate(values)
    ]


def test_long_stable_work_phase_has_interpretable_hr_drift():
    power = (
        [108] * 300
        + [107] * 300
    )

    heart_rate = (
        [130] * 300
        + [138] * 300
    )

    cadence = [18] * 600

    result = _phase_metrics(
        name="work_1",
        start_seconds=0,
        end_seconds=600,
        stream_start=START,
        streams={
            "power": stream(power),
            "heart_rate":
                stream(heart_rate),
            "cadence":
                stream(cadence),
        },
        target_power=(105, 110),
    )

    assert (
        result["power_change_watts"]
        == -1.0
    )

    assert (
        result["power_change_percent"]
        == -0.9
    )

    assert (
        result["heart_rate_drift_bpm"]
        == 8.0
    )

    assert (
        result["heart_rate_drift_percent"]
        == 6.2
    )

    assert (
        result[
            "heart_rate_drift_interpretable"
        ]
        is True
    )

def test_phase_metrics_describe_stable_power_and_rising_hr():
    power = (
        [100] * 300
        + [104] * 300
    )

    heart_rate = (
        [130] * 300
        + [138] * 300
    )

    result = _phase_metrics(
        name="work",
        start_seconds=0,
        end_seconds=600,
        stream_start=START,
        streams={
            "power": stream(power),
            "heart_rate":
                stream(heart_rate),
            "cadence":
                stream([18] * 600),
        },
    )

    assert result["power_change_percent"] == 4.0
    assert result["power_trend"] == "stable"

    assert result["heart_rate_drift_bpm"] == 8.0
    assert result["heart_rate_trend"] == "rising"


def test_phase_metrics_describe_rising_power():
    power = (
        [100] * 300
        + [106] * 300
    )

    result = _phase_metrics(
        name="work",
        start_seconds=0,
        end_seconds=600,
        stream_start=START,
        streams={
            "power": stream(power),
            "heart_rate":
                stream([130] * 600),
            "cadence":
                stream([18] * 600),
        },
    )

    assert result["power_change_percent"] == 6.0
    assert result["power_trend"] == "rising"


def test_phase_metrics_describe_falling_power_and_hr():
    power = (
        [100] * 300
        + [94] * 300
    )

    heart_rate = (
        [140] * 300
        + [136] * 300
    )

    result = _phase_metrics(
        name="work",
        start_seconds=0,
        end_seconds=600,
        stream_start=START,
        streams={
            "power": stream(power),
            "heart_rate":
                stream(heart_rate),
            "cadence":
                stream([18] * 600),
        },
    )

    assert result["power_change_percent"] == -6.0
    assert result["power_trend"] == "falling"

    assert result["heart_rate_drift_bpm"] == -4.0
    assert result["heart_rate_trend"] == "falling"

def test_short_work_phase_hr_drift_is_not_interpretable():
    result = _phase_metrics(
        name="work_1",
        start_seconds=0,
        end_seconds=180,
        stream_start=START,
        streams={
            "power":
                stream([140] * 180),
            "heart_rate":
                stream([140] * 180),
            "cadence":
                stream([18] * 180),
        },
    )

    assert (
        result[
            "heart_rate_drift_interpretable"
        ]
        is False
    )


def test_warmup_hr_drift_is_not_interpretable():
    result = _phase_metrics(
        name="warmup",
        start_seconds=0,
        end_seconds=600,
        stream_start=START,
        streams={
            "power":
                stream([100] * 600),
            "heart_rate":
                stream([130] * 600),
            "cadence":
                stream([18] * 600),
        },
    )

    assert (
        result[
            "heart_rate_drift_interpretable"
        ]
        is False
    )


def test_hr_drift_with_large_power_change_is_not_interpretable():
    power = (
        [100] * 300
        + [120] * 300
    )

    heart_rate = (
        [130] * 300
        + [140] * 300
    )

    result = _phase_metrics(
        name="work",
        start_seconds=0,
        end_seconds=600,
        stream_start=START,
        streams={
            "power": stream(power),
            "heart_rate":
                stream(heart_rate),
            "cadence":
                stream([18] * 600),
        },
    )

    assert (
        result["power_change_percent"]
        == 20.0
    )

    assert (
        result[
            "heart_rate_drift_interpretable"
        ]
        is False
    )

def test_max_rolling_average_ignores_single_peak():
    values = [
        140,
        141,
        142,
        180,
        143,
        142,
        141,
    ]

    result = _max_rolling_average(
        values,
        window_size=5,
    )

    assert result == 149.6

def test_interval_phases_include_last_recovery():
    seconds = 2529

    streams = {
        "heart_rate":
            stream([130] * seconds),
        "power":
            stream([135] * seconds),
        "cadence":
            stream([18] * seconds),
    }

    result = analyze_workout_phases(
        warmup="7m",
        repeat=6,
        work="3m,135-145w",
        recovery="2m,90-100w",
        cooldown="5m",
        streams=streams,
    )

    assert (
        result["planned_duration_seconds"]
        == 2520
    )

    names = [
        phase["name"]
        for phase in result["phases"]
    ]

    assert "recovery_6" in names

    recovery_6 = next(
        phase
        for phase in result["phases"]
        if phase["name"] == "recovery_6"
    )

    assert recovery_6["start_seconds"] == 2100
    assert recovery_6["end_seconds"] == 2220

    cooldown = next(
        phase
        for phase in result["phases"]
        if phase["name"] == "cooldown"
    )

    assert cooldown["start_seconds"] == 2220
    assert cooldown["end_seconds"] == 2520

def test_interval_recovery_uses_work_peak_and_end_windows():
    heart_rate = (
        [100] * 60
        # work_1
        + [140] * 30
        + [145] * 30
        # recovery_1
        + [150] * 5
        + [145] * 25
        + [125] * 30
        # work_2
        + [140] * 60
        # recovery_2
        + [145] * 5
        + [140] * 25
        + [120] * 30
    )

    result = _analyze_interval_recovery(
        stream_start=START,
        streams={
            "heart_rate":
                stream(heart_rate),
            "power": [],
            "cadence": [],
        },
        warmup_seconds=60,
        repeat=2,
        work_seconds=60,
        recovery_seconds=60,
    )

    assert len(result) == 2

    recovery = result[0]

    assert (
        recovery["repetition"]
        == 1
    )

    assert (
        recovery["heart_rate_work_end"]
        == 145.0
    )

    assert (
        recovery[
            "heart_rate_recovery_peak"
        ]
        == 150.0
    )

    assert (
        recovery[
            "heart_rate_recovery_end"
        ]
        == 125.0
    )

    assert (
        recovery[
            "heart_rate_recovery_bpm"
        ]
        == 25.0
    )

    recovery = result[1]

    assert (
        recovery["repetition"]
        == 2
    )

    assert (
        recovery["work_phase"]
        == "work_2"
    )

    assert (
        recovery["recovery_phase"]
        == "recovery_2"
    )

    assert (
        recovery["heart_rate_work_end"]
        == 140.0
    )

    assert (
        recovery[
            "heart_rate_recovery_peak"
        ]
        == 145.0
    )

    assert (
        recovery[
            "heart_rate_recovery_end"
        ]
        == 120.0
    )

    assert (
        recovery[
            "heart_rate_recovery_bpm"
        ]
        == 25.0
    )