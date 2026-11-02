from heart_rate_zones import (
    build_heart_rate_zones,
)

from heart_rate_zones import (
    analyze_heart_rate_zones,
    build_heart_rate_zones,
    classify_heart_rate,
)


def test_build_max_hr_zones():
    zones = build_heart_rate_zones(
        max_heart_rate=196,
        zone_1_min_percent=50.0,
        zone_2_min_percent=60.0,
        zone_3_min_percent=70.0,
        zone_4_min_percent=80.0,
        zone_5_min_percent=90.0,
    )

    assert [
        (
            zone.name,
            zone.min_bpm,
            zone.max_bpm,
        )
        for zone in zones
    ] == [
        ("zone_1", 98, 117),
        ("zone_2", 118, 136),
        ("zone_3", 137, 156),
        ("zone_4", 157, 175),
        ("zone_5", 176, 196),
    ]

def test_classify_heart_rate():
    zones = build_heart_rate_zones(
        max_heart_rate=196,
        zone_1_min_percent=50.0,
        zone_2_min_percent=60.0,
        zone_3_min_percent=70.0,
        zone_4_min_percent=80.0,
        zone_5_min_percent=90.0,
    )

    assert classify_heart_rate(90, zones) == "below_zone"
    assert classify_heart_rate(98, zones) == "zone_1"
    assert classify_heart_rate(117, zones) == "zone_1"
    assert classify_heart_rate(118, zones) == "zone_2"
    assert classify_heart_rate(136, zones) == "zone_2"
    assert classify_heart_rate(137, zones) == "zone_3"
    assert classify_heart_rate(157, zones) == "zone_4"
    assert classify_heart_rate(176, zones) == "zone_5"
    assert classify_heart_rate(196, zones) == "zone_5"
    assert classify_heart_rate(197, zones) == "above_zone"


def test_analyze_heart_rate_zones():
    zones = build_heart_rate_zones(
        max_heart_rate=196,
        zone_1_min_percent=50.0,
        zone_2_min_percent=60.0,
        zone_3_min_percent=70.0,
        zone_4_min_percent=80.0,
        zone_5_min_percent=90.0,
    )

    values = (
        [110] * 10
        + [130] * 60
        + [145] * 30
    )

    result = analyze_heart_rate_zones(
        values,
        zones,
    )

    assert result["sample_count"] == 100
    assert result["dominant_zone"] == "zone_2"

    assert (
        result["distribution"]["zone_1"]["seconds"]
        == 10
    )

    assert (
        result["distribution"]["zone_2"]["seconds"]
        == 60
    )

    assert (
        result["distribution"]["zone_3"]["seconds"]
        == 30
    )

    assert (
        result["distribution"]["zone_2"]["percent"]
        == 60.0
    )