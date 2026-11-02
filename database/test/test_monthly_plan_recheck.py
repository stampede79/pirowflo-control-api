from monthly_plan_recheck import (
    _reassessment_signals,
)


def test_low_load_with_positive_progression_is_ok():
    result = _reassessment_signals(
        assessment="mixed",
        trend="improving",
        load_assessment="low",
        recovery_assessment="watch",
        progression="positive",
    )

    assert result == []


def test_low_load_with_declining_trend_requires_reassessment():
    result = _reassessment_signals(
        assessment="mixed",
        trend="declining",
        load_assessment="low",
        recovery_assessment="good",
        progression="stable",
    )

    assert (
        "monthly_trend_declining"
        in result
    )

    assert (
        "monthly_load_low_with_concern"
        in result
    )


def test_high_load_requires_reassessment():
    result = _reassessment_signals(
        assessment="good",
        trend="stable",
        load_assessment="high",
        recovery_assessment="good",
        progression="stable",
    )

    assert result == [
        "monthly_load_high",
    ]


def test_concerning_recovery_requires_reassessment():
    result = _reassessment_signals(
        assessment="mixed",
        trend="stable",
        load_assessment="appropriate",
        recovery_assessment="concerning",
        progression="stable",
    )

    assert result == [
        "monthly_recovery_concerning",
    ]