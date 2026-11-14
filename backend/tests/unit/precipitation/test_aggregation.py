from datetime import date

import pytest

from app.precipitation.aggregation import (
    aggregate_precipitation_years,
    monthly_rate_to_accumulation,
)
from app.precipitation.models import (
    MonthlyPrecipitation,
    MonthlyPrecipitationSeries,
    PrecipitationPolicy,
    PrecipitationQuery,
)


@pytest.mark.parametrize(("year", "month", "expected"), [(2019, 2, 672), (2020, 2, 696), (2020, 4, 720), (2020, 1, 744)])
def test_calendar_month_conversion(year: int, month: int, expected: float) -> None:
    assert monthly_rate_to_accumulation(1.0, year, month) == expected


def test_conversion_rejects_invalid_rate() -> None:
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            monthly_rate_to_accumulation(value, 2020, 1)


def _series(missing: int | None = None, masked: int | None = None) -> MonthlyPrecipitationSeries:
    rows = []
    for month in range(1, 13):
        if month == missing:
            continue
        rate = None if month == masked else 1.0
        rows.append(MonthlyPrecipitation(date(2020, month, 1), rate, None if rate is None else monthly_rate_to_accumulation(rate, 2020, month), True))
    return MonthlyPrecipitationSeries(tuple(rows), "16.85,96.15")


def test_complete_year_is_eligible_and_sums_calendar_hours() -> None:
    query = PrecipitationQuery(16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1))
    summary = aggregate_precipitation_years(_series(), query, PrecipitationPolicy())[0]
    assert summary.annual_accumulation_mm == 8784
    assert summary.observed_accumulation_mm == 8784
    assert summary.eligible_for_trend_inference is True


def test_missing_catalog_month_differs_from_masked_value() -> None:
    query = PrecipitationQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1))
    catalog = aggregate_precipitation_years(_series(missing=3), query, PrecipitationPolicy())[0]
    masked = aggregate_precipitation_years(_series(masked=3), query, PrecipitationPolicy())[0]
    assert catalog.annual_accumulation_mm is None
    assert catalog.eligibility_reasons == ("missing_catalog_month", "insufficient_valid_months")
    assert masked.eligibility_reasons == ("missing_monthly_value", "insufficient_valid_months")
    assert catalog.observed_accumulation_mm > 0


def test_partial_calendar_year_remains_descriptive() -> None:
    query = PrecipitationQuery(0, 0, date(2020, 2, 1), date(2021, 1, 1))
    summary = aggregate_precipitation_years(_series(), query, PrecipitationPolicy())[0]
    assert summary.eligible_for_trend_inference is False
    assert "partial_calendar_year" in summary.eligibility_reasons


def test_policy_cannot_make_an_eleven_month_total_trend_eligible() -> None:
    query = PrecipitationQuery(0, 0, date(2020, 1, 1), date(2021, 1, 1))
    summary = aggregate_precipitation_years(_series(missing=3), query, PrecipitationPolicy(minimum_valid_months=11))[0]
    assert summary.annual_accumulation_mm is None
    assert summary.eligible_for_trend_inference is False
    assert "insufficient_valid_months" in summary.eligibility_reasons

