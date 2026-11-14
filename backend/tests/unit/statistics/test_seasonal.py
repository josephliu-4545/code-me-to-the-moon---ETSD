import math

import pytest

from app.statistics.policies import TrendPolicy
from app.statistics.seasonal import deseasonalized_ols_slope, seasonal_trend

MONSOON = {6, 7, 8, 9, 10}


def test_hand_computed_score_variance_and_slope() -> None:
    # Jan: 1, 2, 4 -> S=+3, slopes 1, 1.5, 3. Feb: 5, 3, 4 -> S=-1, slopes -2, -0.5, 1.
    monthly = {(2015, 1): 1.0, (2016, 1): 2.0, (2017, 1): 4.0, (2015, 2): 5.0, (2016, 2): 3.0, (2017, 2): 4.0}
    trend, months = seasonal_trend(monthly, 2015, 2017, "u", TrendPolicy(minimum_slope_years=3, minimum_significance_years=3))

    assert months == [1, 2]
    assert trend.result_level == "statistical_inference"
    assert trend.mann_kendall.s == 2
    assert trend.mann_kendall.variance == pytest.approx(2 * (3 * 2 * 11) / 18)
    assert trend.mann_kendall.tau == pytest.approx(2 / 6)
    assert trend.theil_sen.slope == pytest.approx(1.0)


def test_monsoon_gaps_still_detect_trend_and_exclude_sparse_months() -> None:
    noise = [0.004, -0.003, 0.001, -0.004, 0.002, 0.003, -0.002, 0.0, -0.001, 0.002]
    monthly = {
        (year, month): 0.5 + 0.05 * math.sin(month) + 0.003 * (year - 2015) + noise[(year + month) % 10]
        for year in range(2015, 2025)
        for month in range(1, 13)
        if month not in MONSOON or year in (2016, 2020)  # monsoon months seen in only 2 of 10 years
    }
    trend, months = seasonal_trend(monthly, 2015, 2024, "NDVI", TrendPolicy())

    assert months == [1, 2, 3, 4, 5, 11, 12]
    assert trend.result_level == "statistical_inference"
    assert trend.mann_kendall.direction == "increasing"
    assert trend.theil_sen.slope == pytest.approx(0.003, abs=0.001)
    low, high = trend.theil_sen.confidence_interval
    assert low < trend.theil_sen.slope < high
    assert deseasonalized_ols_slope(monthly, months) == pytest.approx(0.003, abs=0.001)


def test_too_few_years_gives_descriptive_slope_only() -> None:
    monthly = {(year, month): 0.5 + 0.01 * (year - 2015) for year in range(2015, 2020) for month in (1, 2, 3)}
    trend, _ = seasonal_trend(monthly, 2015, 2019, "NDVI", TrendPolicy())
    assert trend.result_level == "descriptive_slope"
    assert trend.mann_kendall is None
    assert trend.theil_sen.slope == pytest.approx(0.01)
    assert "8 years" in trend.significance_unavailable_reason


def test_no_month_with_enough_years() -> None:
    trend, months = seasonal_trend({(2015, 1): 0.5, (2016, 1): 0.6}, 2015, 2024, "NDVI", TrendPolicy())
    assert months == []
    assert trend.result_level == "annual_summaries_only"
    assert trend.theil_sen is None
