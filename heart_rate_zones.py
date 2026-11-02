from dataclasses import dataclass

from database.engine import SessionLocal
from database.models import AthleteProfile


@dataclass(frozen=True)
class HeartRateZone:
    name: str
    min_bpm: int
    max_bpm: int


def get_athlete_profile() -> AthleteProfile | None:
    with SessionLocal() as session:
        return session.get(
            AthleteProfile,
            1,
        )


def build_heart_rate_zones(
    *,
    max_heart_rate: int,
    zone_1_min_percent: float,
    zone_2_min_percent: float,
    zone_3_min_percent: float,
    zone_4_min_percent: float,
    zone_5_min_percent: float,
) -> list[HeartRateZone]:
    thresholds = [
        round(
            max_heart_rate
            * zone_1_min_percent
            / 100
        ),
        round(
            max_heart_rate
            * zone_2_min_percent
            / 100
        ),
        round(
            max_heart_rate
            * zone_3_min_percent
            / 100
        ),
        round(
            max_heart_rate
            * zone_4_min_percent
            / 100
        ),
        round(
            max_heart_rate
            * zone_5_min_percent
            / 100
        ),
    ]

    return [
        HeartRateZone(
            name="zone_1",
            min_bpm=thresholds[0],
            max_bpm=thresholds[1] - 1,
        ),
        HeartRateZone(
            name="zone_2",
            min_bpm=thresholds[1],
            max_bpm=thresholds[2] - 1,
        ),
        HeartRateZone(
            name="zone_3",
            min_bpm=thresholds[2],
            max_bpm=thresholds[3] - 1,
        ),
        HeartRateZone(
            name="zone_4",
            min_bpm=thresholds[3],
            max_bpm=thresholds[4] - 1,
        ),
        HeartRateZone(
            name="zone_5",
            min_bpm=thresholds[4],
            max_bpm=max_heart_rate,
        ),
    ]


def get_configured_heart_rate_zones(
) -> list[HeartRateZone] | None:
    profile = get_athlete_profile()

    if (
        profile is None
        or profile.max_heart_rate is None
        or profile.heart_rate_zone_method
        != "max_hr"
    ):
        return None

    return build_heart_rate_zones(
        max_heart_rate=profile.max_heart_rate,
        zone_1_min_percent=
            profile.zone_1_min_percent,
        zone_2_min_percent=
            profile.zone_2_min_percent,
        zone_3_min_percent=
            profile.zone_3_min_percent,
        zone_4_min_percent=
            profile.zone_4_min_percent,
        zone_5_min_percent=
            profile.zone_5_min_percent,
    )

def classify_heart_rate(
    heart_rate: float,
    zones: list[HeartRateZone],
) -> str:
    if not zones:
        return "unknown"

    if heart_rate < zones[0].min_bpm:
        return "below_zone"

    for zone in zones:
        if (
            heart_rate >= zone.min_bpm
            and heart_rate <= zone.max_bpm
        ):
            return zone.name

    return "above_zone"


def analyze_heart_rate_zones(
    values: list[float],
    zones: list[HeartRateZone],
) -> dict:
    counts = {
        "below_zone": 0,
        "zone_1": 0,
        "zone_2": 0,
        "zone_3": 0,
        "zone_4": 0,
        "zone_5": 0,
        "above_zone": 0,
    }

    for value in values:
        zone_name = classify_heart_rate(
            value,
            zones,
        )

        counts[zone_name] += 1

    total = len(values)

    distribution = {
        name: {
            "seconds": seconds,
            "percent": (
                round(
                    seconds / total * 100,
                    1,
                )
                if total
                else 0.0
            ),
        }
        for name, seconds in counts.items()
    }

    physiological_zones = [
        "zone_1",
        "zone_2",
        "zone_3",
        "zone_4",
        "zone_5",
    ]

    dominant_zone = max(
        physiological_zones,
        key=lambda name: counts[name],
        default=None,
    )

    if (
        dominant_zone is not None
        and counts[dominant_zone] == 0
    ):
        dominant_zone = None

    return {
        "sample_count": total,
        "distribution": distribution,
        "dominant_zone": dominant_zone,
    }