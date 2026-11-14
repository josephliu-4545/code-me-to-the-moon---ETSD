import pytest
from scipy.stats import kendalltau, theilslopes

from app.statistics.models import AnnualSummary
from app.statistics.policies import TrendPolicy
from app.statistics.trend import _mann_kendall, analyze_trend


def annual(year: int, value: float) -> AnnualSummary:
    return AnnualSummary(
        year=year,
        annual_value=value,
        value_units="NDVI units",
        monthly_values=((1, value),),
        represented_months=(1,),
        missing_months=tuple(range(2, 13)),
        represented_quarters=(1,),
        missing_quarters=(2, 3, 4),
        valid_observations=1,
        used_observations=1,
        expected_observations=1,
        available_images=1,
        valid_coverage_percentage=100,
        image_availability_percentage=100,
        is_complete_calendar_year=True,
        eligible_for_trend_inference=True,
        eligibility_reasons=(),
        minimum_spatial_coverage_percentage=None,
        mean_spatial_coverage_percentage=None,
        median_spatial_coverage_percentage=None,
        spatial_coverage_threshold_applied=None,
    )


def test_noisy_theil_sen_matches_scipy_with_actual_years() -> None:
    years = (2000, 2001, 2003, 2006, 2007, 2010)
    values = (0.20, 0.24, 0.22, 0.39, 0.35, 0.51)
    expected = theilslopes(values, x=years, alpha=0.95, method="separate")

    result = analyze_trend(
        tuple(annual(year, value) for year, value in zip(years, values, strict=True)),
        "NDVI units",
        TrendPolicy(),
    )

    assert result.theil_sen.slope == pytest.approx(expected.slope)
    assert result.theil_sen.intercept == pytest.approx(expected.intercept)


def test_tie_corrected_kendall_tau_matches_scipy_tau_b() -> None:
    values = [1.0, 1.0, 2.0, 3.0, 3.0, 4.0, 5.0, 5.0]
    expected = kendalltau(
        list(range(len(values))),
        values,
        variant="b",
        method="asymptotic",
        alternative="two-sided",
    )

    result = _mann_kendall(values, alpha=0.05)

    assert result is not None
    assert result.tau == pytest.approx(expected.statistic)
    assert 0 <= result.p_value <= 1

