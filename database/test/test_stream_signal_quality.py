from datetime import (
    datetime,
    timedelta,
)

from stream_signal_quality import (
    clean_cadence_stream,
    clean_heart_rate_stream,
    clean_power_stream,
    clean_activity_streams,
)



START = datetime(
    2026,
    10,
    28,
    10,
    0,
)


def points(values):
    return [
        {
            "time":
                START + timedelta(seconds=index),
            "value":
                value,
        }
        for index, value in enumerate(values)
    ]


def values(result):
    return [
        point["value"]
        for point in result.points
    ]


def test_normal_heart_rate_is_unchanged():
    raw = points([
        132,
        133,
        134,
        135,
        136,
        137,
    ])

    result = clean_heart_rate_stream(raw)

    assert values(result) == [
        132,
        133,
        134,
        135,
        136,
        137,
    ]

    assert result.quality.excluded_samples == 0
    assert result.quality.quality == "good"


def test_isolated_heart_rate_spike_is_removed():
    raw = points([
        138,
        139,
        140,
        218,
        141,
        142,
    ])

    result = clean_heart_rate_stream(raw)

    assert 218 not in values(result)
    assert result.quality.excluded_samples == 1


def test_real_heart_rate_increase_is_kept():
    raw = points([
        140,
        145,
        155,
        170,
        185,
        195,
        188,
    ])

    result = clean_heart_rate_stream(raw)

    assert values(result) == [
        140,
        145,
        155,
        170,
        185,
        195,
        188,
    ]


def test_isolated_power_spike_is_removed():
    raw = points([
        138,
        140,
        139,
        620,
        141,
        140,
    ])

    result = clean_power_stream(raw)

    assert 620 not in values(result)
    assert result.quality.excluded_samples == 1


def test_real_power_sprint_is_kept():
    raw = points([
        140,
        160,
        205,
        250,
        230,
        190,
        150,
    ])

    result = clean_power_stream(raw)

    assert values(result) == [
        140,
        160,
        205,
        250,
        230,
        190,
        150,
    ]


def test_single_power_dropout_is_removed():
    raw = points([
        138,
        140,
        0,
        141,
        139,
    ])

    result = clean_power_stream(raw)

    assert values(result) == [
        138,
        140,
        141,
        139,
    ]


def test_real_power_pause_is_kept():
    raw = points([
        140,
        135,
        0,
        0,
        0,
        90,
        95,
    ])

    result = clean_power_stream(raw)

    assert values(result) == [
        140,
        135,
        0,
        0,
        0,
        90,
        95,
    ]


def test_single_cadence_dropout_is_removed():
    raw = points([
        18,
        18,
        0,
        18,
        19,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        18,
        18,
        18,
        19,
    ]


def test_real_cadence_stop_is_kept():
    raw = points([
        18,
        17,
        0,
        0,
        0,
        16,
        17,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        18,
        17,
        0,
        0,
        0,
        16,
        17,
    ]

def test_real_start_artifact_67_spm_is_removed():
    raw = points([
        0,
        0,
        0,
        30,
        67,
        67,
        67,
        19,
        19,
        19,
        17,
        17,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        0,
        0,
        0,
        19,
        19,
        19,
        17,
        17,
    ]


def test_real_start_artifact_48_spm_is_removed():
    raw = points([
        0,
        0,
        0,
        48,
        48,
        48,
        48,
        20,
        20,
        20,
        21,
        21,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        0,
        0,
        0,
        20,
        20,
        20,
        21,
        21,
    ]


def test_real_start_artifact_46_spm_is_removed():
    raw = points([
        0,
        0,
        0,
        46,
        46,
        46,
        46,
        46,
        46,
        21,
        21,
        17,
        17,
        17,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        0,
        0,
        0,
        21,
        21,
        17,
        17,
        17,
    ]


def test_real_start_artifact_36_spm_is_removed():
    raw = points([
        0,
        0,
        0,
        36,
        36,
        36,
        36,
        19,
        19,
        19,
        18,
        18,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        0,
        0,
        0,
        19,
        19,
        19,
        18,
        18,
    ]


def test_normal_22_spm_start_is_kept():
    raw = points([
        0,
        0,
        0,
        22,
        22,
        22,
        20,
        20,
        20,
        18,
        18,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        0,
        0,
        0,
        22,
        22,
        22,
        20,
        20,
        20,
        18,
        18,
    ]


def test_normal_restart_is_kept():
    raw = points([
        0,
        0,
        0,
        17,
        17,
        17,
        17,
        21,
        21,
        21,
        20,
        20,
    ])

    result = clean_cadence_stream(raw)

    assert values(result) == [
        0,
        0,
        0,
        17,
        17,
        17,
        17,
        21,
        21,
        21,
        20,
        20,
    ]

def test_clean_activity_streams_cleans_all_streams():
    raw_streams = {
        "heart_rate": points([
            138,
            139,
            218,
            140,
            141,
        ]),
        "power": points([
            100,
            102,
            600,
            103,
            104,
        ]),
        "cadence": points([
            0,
            0,
            0,
            48,
            48,
            48,
            48,
            20,
            20,
            20,
        ]),
    }

    result = clean_activity_streams(
        raw_streams
    )

    assert 218 not in [
        point["value"]
        for point
        in result.streams["heart_rate"]
    ]

    assert 600 not in [
        point["value"]
        for point
        in result.streams["power"]
    ]

    assert 48 not in [
        point["value"]
        for point
        in result.streams["cadence"]
    ]

    assert (
        result.quality["heart_rate"]
        .excluded_samples
        == 1
    )

    assert (
        result.quality["power"]
        .excluded_samples
        == 1
    )

    assert (
        result.quality["cadence"]
        .excluded_samples
        == 4
    )


def test_clean_activity_streams_handles_missing_stream():
    raw_streams = {
        "power": points([
            100,
            101,
            102,
        ]),
    }

    result = clean_activity_streams(
        raw_streams
    )

    assert result.streams["heart_rate"] == []
    assert result.streams["cadence"] == []

    assert (
        result.quality["heart_rate"]
        .raw_samples
        == 0
    )

    assert (
        result.quality["cadence"]
        .raw_samples
        == 0
    )

def test_coupled_start_artifact_removes_power_plateau():
    raw_streams = {
        "heart_rate": points([
            100, 101, 102, 103,
            104, 105, 106, 107,
            108, 109, 110, 111,
        ]),
        "cadence": points([
            0,
            0,
            0,
            30,
            67,
            67,
            67,
            19,
            19,
            19,
            17,
            17,
        ]),
        "power": points([
            0,
            0,
            0,
            9,
            192,
            192,
            192,
            66,
            66,
            66,
            62,
            62,
        ]),
    }

    result = clean_activity_streams(
        raw_streams
    )

    assert [
    point["value"]
    for point in result.streams["power"]
] == [
        0,
        0,
        0,
        9,
        66,
        66,
        66,
        62,
        62,
    ]

    assert (
        result.quality["power"]
        .excluded_samples
        == 3
    )

def test_cadence_artifact_does_not_remove_valid_low_power():
    raw_streams = {
        "heart_rate": points([
            100, 101, 102, 103,
            104, 105, 106, 107,
            108, 109, 110, 111,
            112, 113,
        ]),
        "cadence": points([
            0,
            0,
            0,
            46,
            46,
            46,
            46,
            46,
            46,
            21,
            21,
            17,
            17,
            17,
        ]),
        "power": points([
            0,
            3,
            3,
            3,
            8,
            8,
            8,
            8,
            8,
            64,
            64,
            23,
            23,
            23,
        ]),
    }

    result = clean_activity_streams(
        raw_streams
    )

    assert result.quality[
        "power"
    ].excluded_samples == 0

    assert [
    point["value"]
    for point in result.streams["power"]
] == [
        0,
        3,
        3,
        3,
        8,
        8,
        8,
        8,
        8,
        64,
        64,
        23,
        23,
        23,
    ]