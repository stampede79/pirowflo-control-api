from datetime import date

from monthly_coach_job import (
    monthly_weekly_reviews_ready,
    next_month_from_year_month,
)


def test_october_not_ready_on_november_first():
    assert (
        monthly_weekly_reviews_ready(
            year=2026,
            month=10,
            today=date(2026, 11, 1),
        )
        is False
    )


def test_october_ready_on_november_second():
    assert (
        monthly_weekly_reviews_ready(
            year=2026,
            month=10,
            today=date(2026, 11, 2),
        )
        is True
    )

def test_next_month_from_year_month_handles_year_change():
    assert (
        next_month_from_year_month(
            2026,
            12,
        )
        == (2027, 1)
    )
