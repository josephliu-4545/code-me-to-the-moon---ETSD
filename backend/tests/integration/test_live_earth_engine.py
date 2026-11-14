from datetime import date
import os

import pytest

from app.core.earth_engine import EarthEngineManager
from app.schemas.ndvi import NDVIQuery
from app.services.modis_service import ModisService
from app.statistics.annual import aggregate_annual
from app.statistics.policies import AnnualAggregationPolicy
from app.precipitation.models import PrecipitationQuery
from app.services.imerg_service import ImergService
from app.services.precipitation_service import PrecipitationService


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_EE_INTEGRATION") != "1" or not os.getenv("EE_PROJECT_ID"),
    reason="set RUN_EE_INTEGRATION=1 and EE_PROJECT_ID to run live Earth Engine tests",
)
def test_live_modis_ndvi_retrieval() -> None:
    manager = EarthEngineManager(os.environ["EE_PROJECT_ID"])
    service = ModisService(manager)
    query = NDVIQuery(
        latitude=16.8661,
        longitude=96.1951,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 4, 1),
        radius_km=5,
    )

    response = service.fetch_ndvi(query)

    assert response.dataset == "NASA MODIS MOD13Q1.061"
    assert response.observation_count == len(response.observations)
    assert response.observation_count > 0
    assert all(-0.2 <= observation.ndvi <= 1.0 for observation in response.observations)
    assert all(
        query.start_date <= observation.date < query.end_date
        for observation in response.observations
    )


@pytest.mark.skipif(
    os.getenv("RUN_EE_INTEGRATION") != "1" or not os.getenv("EE_PROJECT_ID"),
    reason="set RUN_EE_INTEGRATION=1 and EE_PROJECT_ID to run live Earth Engine tests",
)
def test_live_yangon_2020_coverage_and_eligibility() -> None:
    manager = EarthEngineManager(os.environ["EE_PROJECT_ID"])
    service = ModisService(manager)
    query = NDVIQuery(
        latitude=16.8661,
        longitude=96.1951,
        start_date=date(2020, 1, 1),
        end_date=date(2021, 1, 1),
        radius_km=5,
    )

    series = service.fetch_ndvi_series(query)
    summary = aggregate_annual(series, AnnualAggregationPolicy())[0]

    assert len(series.coverage_by_year[0].available_image_dates) == 23
    assert len(series.observations) == 13
    assert all(item.spatial_coverage_percentage is not None for item in series.observations)
    assert all(
        item.valid_pixel_count <= item.total_pixel_count
        and 0 <= item.spatial_coverage_percentage <= 100
        for item in series.observations
    )
    assert summary.valid_coverage_percentage == pytest.approx(13 / 23 * 100)
    assert summary.minimum_spatial_coverage_percentage == pytest.approx(
        15.204236006051437
    )
    assert summary.mean_spatial_coverage_percentage == pytest.approx(
        29.427179855172636
    )
    assert summary.represented_months == (1, 2, 3, 4, 5, 10, 11, 12)
    assert summary.eligible_for_trend_inference is False
    assert summary.eligibility_reasons == (
        "insufficient_represented_months",
        "insufficient_valid_slot_coverage",
        "missing_calendar_quarter",
    )


@pytest.mark.skipif(
    os.getenv("RUN_EE_INTEGRATION") != "1" or not os.getenv("EE_PROJECT_ID"),
    reason="set RUN_EE_INTEGRATION=1 and EE_PROJECT_ID to run live Earth Engine tests",
)
def test_live_yangon_imerg_v07_precipitation_2015_2025() -> None:
    manager = EarthEngineManager(os.environ["EE_PROJECT_ID"])
    result = PrecipitationService(ImergService(manager)).analyze(
        PrecipitationQuery(
            latitude=16.8661,
            longitude=96.1951,
            start_date=date(2015, 1, 1),
            end_date=date(2025, 1, 1),
        )
    )
    assert len(result.series.observations) == 120
    assert all(item.dataset_id == "NASA/GPM_L3/IMERG_MONTHLY_V07" for item in result.series.observations)
    assert all(item.mean_rate_mm_per_hour is not None and item.mean_rate_mm_per_hour >= 0 for item in result.series.observations)
    assert len(result.annual_summaries) == 10
    assert all(item.eligible_for_trend_inference for item in result.annual_summaries)
    assert result.trend.theil_sen is not None

