"""Opt-in live checks of the alternative datasets used by /api/v2/compare."""

from datetime import date
import os

import pytest

from app.comparison.catalog import find
from app.comparison.providers import EEMonthlyProvider, analyze_months
from app.core.earth_engine import EarthEngineManager
from app.services.soil_moisture_provider import UnsupportedLocationError


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_EE_INTEGRATION") != "1" or not os.getenv("EE_PROJECT_ID"),
        reason="set RUN_EE_INTEGRATION=1 and EE_PROJECT_ID to run live Earth Engine tests",
    ),
]


@pytest.fixture(scope="module")
def provider() -> EEMonthlyProvider:
    return EEMonthlyProvider(EarthEngineManager(os.environ["EE_PROJECT_ID"]))


@pytest.mark.parametrize(
    "variable, key, low, high",
    [
        ("temperature", "gldas_2_1_tair", 20.0, 35.0),
        ("temperature", "era5_land_t2m", 20.0, 35.0),
        ("precipitation", "chirps_v2_daily", 500.0, 6000.0),
        ("precipitation", "era5_land_tp", 500.0, 6000.0),
    ],
)
def test_live_alternative_dataset_year_at_yangon(provider, variable, key, low, high) -> None:
    entry = find(variable, key)
    result = provider.fetch(entry, 16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1))
    assert len(result.months) == 12
    assert all(m.status == "valid" for m in result.months)
    (summary,), trend = analyze_months(entry, list(result.months))
    assert summary.eligible_for_trend_inference
    assert low < summary.annual_value < high


def test_live_chirps_refuses_high_latitude(provider) -> None:
    with pytest.raises(UnsupportedLocationError):
        provider.fetch(find("precipitation", "chirps_v2_daily"), 60.17, 24.94, date(2020, 1, 1), date(2021, 1, 1))


def test_live_gldas_air_temperature_over_ocean_has_no_values(provider) -> None:
    result = provider.fetch(find("temperature", "gldas_2_1_tair"), 0.0, -30.0, date(2020, 1, 1), date(2020, 4, 1))
    assert all(m.value is None for m in result.months)
