from datetime import date

from app.precipitation.aggregation import aggregate_precipitation_years, monthly_rate_to_accumulation
from app.precipitation.models import MonthlyPrecipitation, MonthlyPrecipitationSeries, PrecipitationPolicy, PrecipitationQuery


def test_independent_calendar_hour_example() -> None:
    expected_hours = [31 * 24, 29 * 24, 31 * 24, 30 * 24, 31 * 24, 30 * 24, 31 * 24, 31 * 24, 30 * 24, 31 * 24, 30 * 24, 31 * 24]
    calculated = [monthly_rate_to_accumulation(1.0, 2020, month) for month in range(1, 13)]
    assert calculated == expected_hours
    assert sum(calculated) == 366 * 24


def test_independent_annual_sum_uses_each_month_once() -> None:
    rows = tuple(
        MonthlyPrecipitation(date(2021, month, 1), month / 10, month / 10 * 24 * [31,28,31,30,31,30,31,31,30,31,30,31][month - 1], True)
        for month in range(1, 13)
    )
    expected = sum(month / 10 * 24 * days for month, days in enumerate([31,28,31,30,31,30,31,31,30,31,30,31], 1))
    result = aggregate_precipitation_years(
        MonthlyPrecipitationSeries(rows, "known"),
        PrecipitationQuery(0, 0, date(2021, 1, 1), date(2022, 1, 1)),
        PrecipitationPolicy(),
    )[0]
    assert result.annual_accumulation_mm == expected

