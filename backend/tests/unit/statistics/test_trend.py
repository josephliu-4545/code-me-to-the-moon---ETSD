from app.statistics.models import AnnualSummary
from app.statistics.policies import TrendPolicy
from app.statistics.trend import analyze_trend


def annual(year: int, value: float, eligible: bool = True) -> AnnualSummary:
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
        valid_coverage_percentage=100.0,
        image_availability_percentage=100.0,
        is_complete_calendar_year=True,
        eligible_for_trend_inference=eligible,
        eligibility_reasons=() if eligible else ("fixture_excluded",),
        minimum_spatial_coverage_percentage=None,
        mean_spatial_coverage_percentage=None,
        median_spatial_coverage_percentage=None,
        spatial_coverage_threshold_applied=None,
    )


def test_three_year_slope_uses_actual_calendar_years() -> None:
    result = analyze_trend(
        (annual(2000, 0.0), annual(2002, 0.2), annual(2005, 0.5)),
        "NDVI units",
        TrendPolicy(),
    )

    assert result.result_level == "descriptive_slope"
    assert result.theil_sen.slope == 0.1
    assert result.theil_sen.slope_units == "NDVI units/year"
    assert result.mann_kendall is None
    assert result.significance_unavailable_reason is not None


def test_fewer_than_three_eligible_years_returns_summaries_only() -> None:
    result = analyze_trend(
        (annual(2020, 0.1), annual(2021, 0.2, eligible=False)),
        "NDVI units",
        TrendPolicy(),
    )
    assert result.result_level == "annual_summaries_only"
    assert result.theil_sen is None


def test_identical_values_return_zero_slope_and_withhold_inference() -> None:
    result = analyze_trend(
        tuple(annual(year, 0.4) for year in range(2010, 2020)),
        "NDVI units",
        TrendPolicy(),
    )
    assert result.theil_sen.slope == 0.0
    assert result.theil_sen.confidence_interval is None
    assert result.mann_kendall is None
    assert "identical" in result.significance_unavailable_reason.lower()


def test_eight_year_monotonic_series_reports_supported_significance() -> None:
    values = (0.008, 0.030, 0.130, 0.253, 0.429, 0.488, 0.570, 0.714)
    result = analyze_trend(
        tuple(annual(2010 + index, value) for index, value in enumerate(values)),
        "NDVI units",
        TrendPolicy(),
    )
    assert result.result_level == "statistical_inference"
    assert result.mann_kendall is not None
    assert result.mann_kendall.p_value < 0.05
    assert result.mann_kendall.alternative == "two-sided"


def test_missing_years_can_withhold_inference_for_too_few_adjacent_pairs() -> None:
    years = (2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014)
    result = analyze_trend(
        tuple(annual(year, index / 10) for index, year in enumerate(years)),
        "NDVI units",
        TrendPolicy(),
    )
    assert result.mann_kendall is None
    assert "adjacent" in result.significance_unavailable_reason.lower()


def test_material_serial_dependence_withholds_p_value() -> None:
    values = (0.0, 0.11, 0.19, 0.31, 0.39, 0.51, 0.59, 0.71, 0.79, 0.91)
    result = analyze_trend(
        tuple(annual(2000 + index, value) for index, value in enumerate(values)),
        "NDVI units",
        TrendPolicy(material_lag1_rho=0.10),
    )
    assert result.serial_dependence is not None
    assert result.mann_kendall is None
    assert result.significance_unavailable_reason is not None

