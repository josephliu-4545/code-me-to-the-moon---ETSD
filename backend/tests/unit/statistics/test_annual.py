from datetime import date, timedelta

import pytest

from app.statistics.annual import aggregate_annual
from app.statistics.models import ObservationSeries, TimedValue, YearCoverage
from app.statistics.policies import AnnualAggregationPolicy


def slots(year: int) -> tuple[date, ...]:
    start = date(year, 1, 1)
    return tuple(start + timedelta(days=16 * index) for index in range(23))


def make_series(
    observations: list[TimedValue],
    *,
    year: int = 2020,
    available: tuple[date, ...] | None = None,
    complete: bool = True,
) -> ObservationSeries:
    expected = slots(year)
    return ObservationSeries(
        variable="NDVI",
        value_units="NDVI units",
        dataset="NASA MODIS MOD13Q1.061",
        observations=tuple(observations),
        coverage_by_year=(
            YearCoverage(
                year=year,
                expected_slot_dates=expected,
                available_image_dates=available or expected,
                is_complete_calendar_year=complete,
            ),
        ),
    )


def test_yangon_2020_summary_is_available_but_ineligible() -> None:
    valid_dates = tuple(
        date.fromisoformat(value)
        for value in (
            "2020-01-01", "2020-01-17", "2020-02-02", "2020-02-18",
            "2020-03-05", "2020-03-21", "2020-04-06", "2020-04-22",
            "2020-05-08", "2020-10-31", "2020-11-16", "2020-12-02",
            "2020-12-18",
        )
    )
    observations = [TimedValue(day, 0.5, 80.0, 100, 125) for day in valid_dates]

    summary = aggregate_annual(make_series(observations), AnnualAggregationPolicy())[0]

    assert summary.annual_value == pytest.approx(0.5)
    assert summary.expected_observations == 23
    assert summary.available_images == 23
    assert summary.valid_observations == 13
    assert summary.valid_coverage_percentage == pytest.approx(13 / 23 * 100)
    assert summary.represented_months == (1, 2, 3, 4, 5, 10, 11, 12)
    assert summary.missing_quarters == (3,)
    assert summary.eligible_for_trend_inference is False
    assert summary.eligibility_reasons == (
        "insufficient_represented_months",
        "insufficient_valid_slot_coverage",
        "missing_calendar_quarter",
    )


def test_monthly_stratification_weights_months_equally() -> None:
    observations = [
        TimedValue(date(2020, 1, 1), 0.0),
        TimedValue(date(2020, 1, 17), 0.0),
        TimedValue(date(2020, 2, 2), 1.0),
    ]
    summary = aggregate_annual(make_series(observations), AnnualAggregationPolicy())[0]

    assert summary.monthly_values == ((1, 0.0), (2, 1.0))
    assert summary.annual_value == pytest.approx(0.5)


def test_partial_year_keeps_descriptive_summary_but_is_ineligible() -> None:
    observations = [TimedValue(day, 0.4) for day in slots(2020)[:18]]
    summary = aggregate_annual(
        make_series(observations, complete=False), AnnualAggregationPolicy()
    )[0]

    assert summary.annual_value == pytest.approx(0.4)
    assert summary.eligible_for_trend_inference is False
    assert "partial_calendar_year" in summary.eligibility_reasons


def test_spatial_coverage_is_reported_without_default_exclusion() -> None:
    observations = [TimedValue(day, 0.4, 20.0, 20, 100) for day in slots(2020)]
    summary = aggregate_annual(make_series(observations), AnnualAggregationPolicy())[0]

    assert summary.minimum_spatial_coverage_percentage == 20.0
    assert summary.mean_spatial_coverage_percentage == 20.0
    assert summary.spatial_coverage_threshold_applied is None
    assert summary.eligible_for_trend_inference is True


def test_nine_month_and_seventy_percent_policy_boundaries() -> None:
    desired_months = {1, 2, 3, 4, 5, 6, 7, 8, 10}
    candidates = [day for day in slots(2020) if day.month in desired_months]
    chosen: list[date] = []
    for month in sorted(desired_months):
        chosen.append(next(day for day in candidates if day.month == month))
    chosen.extend(day for day in candidates if day not in chosen)
    chosen = chosen[:17]
    observations = [TimedValue(day, 0.4) for day in chosen]

    eligible = aggregate_annual(make_series(observations), AnnualAggregationPolicy())[0]
    below_coverage = aggregate_annual(
        make_series([TimedValue(day, 0.4) for day in chosen[:-1]]),
        AnnualAggregationPolicy(),
    )[0]

    assert len(eligible.represented_months) == 9
    assert eligible.valid_observations == 17
    assert eligible.valid_coverage_percentage >= 70
    assert eligible.eligible_for_trend_inference is True
    assert below_coverage.valid_observations == 16
    assert below_coverage.valid_coverage_percentage < 70
    assert "insufficient_valid_slot_coverage" in below_coverage.eligibility_reasons


def test_configured_spatial_threshold_excludes_low_support_values() -> None:
    days = slots(2020)
    observations = [TimedValue(day, 0.4, 80.0, 80, 100) for day in days]
    observations[0] = TimedValue(days[0], 0.9, 10.0, 10, 100)
    policy = AnnualAggregationPolicy(minimum_observation_spatial_coverage=50.0)

    summary = aggregate_annual(make_series(observations), policy)[0]

    assert summary.valid_observations == 23
    assert summary.used_observations == 22
    assert summary.spatial_coverage_threshold_applied == 50.0
    assert "low_spatial_coverage_observations_excluded" in summary.eligibility_reasons


def test_domain_rejects_inconsistent_coverage_metadata() -> None:
    expected = slots(2020)
    with pytest.raises(ValueError, match="available image dates"):
        YearCoverage(
            year=2020,
            expected_slot_dates=expected,
            available_image_dates=(date(2020, 1, 2),),
            is_complete_calendar_year=True,
        )

