from datetime import date

import pytest

from app.precipitation.models import (
    MonthlyPrecipitation,
    MonthlyPrecipitationSeries,
    PrecipitationPolicy,
    PrecipitationQuery,
)


def test_query_is_end_exclusive_and_native_grid_only() -> None:
    query = PrecipitationQuery(16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1))
    assert query.support_type == "native_grid_cell"
    with pytest.raises(ValueError, match="end date"):
        PrecipitationQuery(0, 0, date(2020, 1, 1), date(2020, 1, 1))
    with pytest.raises(ValueError, match="latitude"):
        PrecipitationQuery(91, 0, date(2020, 1, 1), date(2021, 1, 1))


def test_monthly_values_are_finite_nonnegative_and_unique() -> None:
    item = MonthlyPrecipitation(date(2020, 1, 1), 1.0, 744.0, True)
    with pytest.raises(ValueError, match="nonnegative"):
        MonthlyPrecipitation(date(2020, 2, 1), -1.0, -696.0, True)
    with pytest.raises(ValueError, match="unique"):
        MonthlyPrecipitationSeries((item, item), "cell")


def test_policy_requires_twelve_months_by_default() -> None:
    assert PrecipitationPolicy().minimum_valid_months == 12

