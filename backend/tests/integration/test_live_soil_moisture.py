"""Opt-in live checks of GLDAS-2.1 and SMAP L3E retrieval through Earth Engine."""

from datetime import date
import os

import pytest

from app.core.earth_engine import EarthEngineManager
from app.services.soil_moisture_provider import EarthEngineSoilMoistureProvider
from app.services.soil_moisture_service import SoilMoistureService
from app.soil_moisture.models import MonthStatus


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_EE_INTEGRATION") != "1" or not os.getenv("EE_PROJECT_ID"),
        reason="set RUN_EE_INTEGRATION=1 and EE_PROJECT_ID to run live Earth Engine tests",
    ),
]


@pytest.fixture(scope="module")
def service() -> SoilMoistureService:
    return SoilMoistureService(EarthEngineSoilMoistureProvider(EarthEngineManager(os.environ["EE_PROJECT_ID"])))


def test_live_gldas_yangon_year(service) -> None:
    result = service.analyze("gldas_2_1_noah_0_10cm", 16.8661, 96.1951, date(2020, 1, 1), date(2021, 1, 1))
    months = result.analysis.monthly.months
    assert len(months) == 12 and all(m.status is MonthStatus.VALID for m in months)
    assert all(0 < m.mean_native < 100 for m in months)
    assert result.provider.cell.cell_id == "gldas:292:1104"
    assert result.cell_status == "ok"


def test_live_smap_v006_kansas_year(service) -> None:
    result = service.analyze("smap_l3e_v006_am", 38.5, -98.5, date(2020, 1, 1), date(2021, 1, 1))
    valid = [m for m in result.analysis.monthly.months if m.status is MonthStatus.VALID]
    assert len(valid) >= 10
    assert all(0 <= m.mean_native <= 1 for m in valid)
    assert result.provider.diagnostics.get("fill_value_leaks", 0) == 0


def test_live_smap_yangon_cell_is_reported_unavailable(service) -> None:
    result = service.analyze("smap_l3e_v006_am", 16.8661, 96.1951, date(2020, 1, 1), date(2020, 7, 1))
    assert result.cell_status == "no_valid_land_values"
    assert all(m.mean_native is None for m in result.analysis.monthly.months)
