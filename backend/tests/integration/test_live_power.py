from datetime import date
import os
from statistics import mean

import pytest

from app.power.client import PowerClient
from app.power.models import PowerParameter, PowerPointQuery
from app.extremes.hot_days import HotDayPolicy
from app.services.extreme_heat_service import ExtremeHeatService
from app.services.temperature_service import TemperatureService
from app.services.relative_humidity_service import RelativeHumidityService


pytestmark = pytest.mark.power_integration


@pytest.mark.skipif(os.getenv("RUN_POWER_INTEGRATION") != "1", reason="set RUN_POWER_INTEGRATION=1 to call NASA POWER")
def test_live_yangon_rh2m_daily_2020() -> None:
    service = RelativeHumidityService(PowerClient())
    query = PowerPointQuery(16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1), "LST")
    result = service.analyze(query)
    summary = result.annual_summaries[0]
    assert result.series.time_standard == "LST"
    assert result.series.valid_count > 0
    assert all(0 <= item.value <= 100 for item in result.series.observations)
    assert summary.expected_observations == 366
    assert summary.value_units == "%"


@pytest.mark.skipif(os.getenv("RUN_POWER_INTEGRATION") != "1", reason="set RUN_POWER_INTEGRATION=1 to call NASA POWER")
def test_live_monthly_product_matches_daily_derived_months_within_rounding() -> None:
    service = RelativeHumidityService(PowerClient())
    query = PowerPointQuery(16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1), "LST")
    daily = service.fetch_daily(query)
    monthly = service.fetch_monthly(query)
    for month in range(1, 13):
        derived = mean(item.value for item in daily.observations if item.date.month == month)
        official = next(item.value for item in monthly.observations if item.date.month == month)
        assert official == pytest.approx(derived, abs=0.02)


@pytest.mark.skipif(os.getenv("RUN_POWER_INTEGRATION") != "1", reason="set RUN_POWER_INTEGRATION=1 to call NASA POWER")
def test_live_yangon_t2m_daily_and_monthly() -> None:
    service=TemperatureService(PowerClient(window_years=5))
    query=PowerPointQuery(16.8661,96.1951,date(2020,1,1),date(2021,1,1),"LST")
    daily=service.fetch_daily(query); monthly=service.fetch_monthly(query)
    assert daily.time_standard=="LST" and len(daily.observations)==366
    assert len(monthly.observations)==12
    assert all(-100 <= x.value <= 70 for x in daily.observations)
    for month in range(1,13):
        derived=mean(x.value for x in daily.observations if x.date.month==month)
        official=next(x.value for x in monthly.observations if x.date.month==month)
        assert official==pytest.approx(derived,abs=.02)


@pytest.mark.skipif(os.getenv("RUN_POWER_INTEGRATION") != "1", reason="set RUN_POWER_INTEGRATION=1 to call NASA POWER")
def test_live_yangon_extreme_heat_reference_and_2020_transition() -> None:
    service=ExtremeHeatService(PowerClient(window_years=5),HotDayPolicy(bootstrap_repetitions=5,random_seed=17))
    result=service.analyze(PowerPointQuery(16.8661,96.1951,date(2020,1,1),date(2022,1,1),"LST"))
    assert result.reference_complete is True
    assert len(result.thresholds.values)==365
    assert result.annual_summaries[0].bootstrap_adjusted_percentage is not None
    assert result.annual_summaries[1].bootstrap_adjusted_percentage is None
