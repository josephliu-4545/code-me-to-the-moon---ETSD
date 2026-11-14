from datetime import date

import httpx
import pytest

from app.core.operation_runner import BoundedOperationRunner
from app.main import create_app
from app.precipitation.aggregation import monthly_rate_to_accumulation
from app.precipitation.models import MonthlyPrecipitation, MonthlyPrecipitationSeries
from app.services.precipitation_service import PrecipitationService


class Source:
    def fetch_monthly(self, query):
        rows = tuple(
            MonthlyPrecipitation(date(2020, month, 1), 1.0, monthly_rate_to_accumulation(1.0, 2020, month), True)
            for month in range(1, 13)
        )
        return MonthlyPrecipitationSeries(rows, "imerg-v07:1068:2761", (16.85, 96.15))


@pytest.mark.anyio
async def test_precipitation_endpoints_return_native_grid_metadata() -> None:
    app = create_app(
        precipitation_service=PrecipitationService(Source()),
        operation_runner=BoundedOperationRunner(1),
    )
    transport = httpx.ASGITransport(app=app)
    params = {"latitude": 16.8661, "longitude": 96.1951, "start_date": "2020-01-01", "end_date": "2021-01-01"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        observations = await client.get("/api/v1/precipitation", params=params)
        trend = await client.get("/api/v1/precipitation/trend", params=params)
    assert observations.status_code == 200
    body = observations.json()
    assert body["dataset"]["id"] == "NASA/GPM_L3/IMERG_MONTHLY_V07"
    assert body["spatial_support"]["type"] == "native_grid_cell"
    assert body["units"]["monthly_accumulation"] == "mm/month"
    assert len(body["monthly_observations"]) == 12
    assert trend.status_code == 200
    assert trend.json()["annual_summaries"][0]["eligible_for_trend_inference"] is True


@pytest.mark.anyio
async def test_precipitation_validation_and_no_radius_contract() -> None:
    app = create_app(precipitation_service=PrecipitationService(Source()))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        invalid = await client.get("/api/v1/precipitation", params={"latitude": 0, "longitude": 0, "start_date": "2021-01-01", "end_date": "2020-01-01"})
        too_long = await client.get("/api/v1/precipitation", params={"latitude": 0, "longitude": 0, "start_date": "2000-01-01", "end_date": "2040-01-01"})
    assert invalid.status_code == 422
    assert too_long.status_code == 422
    parameters = app.openapi()["paths"]["/api/v1/precipitation"]["get"]["parameters"]
    assert "radius_km" not in {item["name"] for item in parameters}

