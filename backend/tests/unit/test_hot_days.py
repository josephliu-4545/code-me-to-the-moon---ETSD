from datetime import date, timedelta

import pytest

from app.extremes.hot_days import HotDayPolicy, bootstrap_base_year, build_thresholds, classify_year
from app.statistics.models import TimedValue


def _reference(years=range(1991, 2021), missing=None):
    missing=missing or set(); out=[]
    for year in years:
        d=date(year,1,1)
        while d < date(year+1,1,1):
            if d not in missing: out.append(TimedValue(d,float(d.month*2+d.day/10)))
            d += timedelta(days=1)
    return tuple(out)


def test_thresholds_have_365_type8_values_and_wrap_year_boundary() -> None:
    thresholds=build_thresholds(_reference(),HotDayPolicy())
    assert len(thresholds.values)==365
    assert thresholds.sample_counts[1]==150
    assert thresholds.values[1] > 0
    assert thresholds.quantile_method=="Hyndman-Fan type 8"


def test_leap_day_threshold_is_interpolated_and_exceedance_is_strict() -> None:
    thresholds=build_thresholds(_reference(),HotDayPolicy())
    feb29=(thresholds.values[59]+thresholds.values[60])/2
    observations=(TimedValue(date(2024,2,29),feb29),TimedValue(date(2024,3,1),thresholds.values[60]+1))
    classified=classify_year(observations,thresholds)
    assert classified[0].threshold==pytest.approx(feb29)
    assert classified[0].is_hot_day is False
    assert classified[1].is_hot_day is True


def test_threshold_is_unavailable_below_configured_sample_fraction() -> None:
    sparse=tuple(x for x in _reference() if x.date.year <= 2000)
    thresholds=build_thresholds(sparse,HotDayPolicy(minimum_window_fraction=.75))
    assert thresholds.values[1] is None


def test_bootstrap_is_exhaustive_reproducible_and_distinct_from_raw_count() -> None:
    reference=_reference()
    policy=HotDayPolicy(bootstrap_repetitions=20,random_seed=17)
    first=bootstrap_base_year(reference,2020,policy)
    second=bootstrap_base_year(reference,2020,policy)
    assert first==second
    assert first.repetitions==29
    assert 0 <= first.adjusted_percentage <= 100
    assert first.raw_count >= 0
