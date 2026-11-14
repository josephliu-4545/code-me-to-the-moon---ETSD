from datetime import date

import httpx
import pytest

from app.core.config import Settings
from app.core.operation_runner import BoundedOperationRunner
from app.main import create_app
from app.power.models import PowerPayload
from app.services.relative_humidity_service import RelativeHumidityService


class FakeClient:
    def fetch_daily_point(self, query, parameter=None):
        return PowerPayload({"20200101": 70.0, "20200102": -999}, "%", -999)

    def fetch_monthly_point(self, query, parameter=None):
        return PowerPayload({"202001": 70.0, "202002": 72.0, "202013": 71.0}, "%", -999, "LST")


@pytest.fixture
def app():
    runner = BoundedOperationRunner(1, operation_name="NASA POWER", thread_name_prefix="nasa-power")
    application = create_app(
        settings=Settings(power_max_date_range_years=50),
        relative_humidity_service=RelativeHumidityService(FakeClient()),
        power_operation_runner=runner,
    )
    yield application
    runner.shutdown()


@pytest.mark.anyio
async def test_daily_endpoint_returns_metadata_coverage_and_lst(app) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/relative-humidity", params={
            "latitude": 16.8661, "longitude": 96.1951,
            "start_date": "2020-01-01", "end_date": "2020-01-03",
            "temporal_resolution": "daily",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["dataset"] == "NASA POWER"
    assert body["parameter"] == "RH2M"
    assert body["units"] == "%"
    assert body["time_standard"] == "LST"
    assert body["coverage"]["expected"] == 2
    assert body["coverage"]["valid"] == 1
    assert "civil time" in " ".join(body["limitations"]).lower()


@pytest.mark.anyio
async def test_monthly_endpoint_omits_power_annual_pseudo_month(app) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/relative-humidity", params={
            "latitude": 0, "longitude": 0, "start_date": "2020-01-01", "end_date": "2020-03-01",
            "temporal_resolution": "monthly", "time_standard": "UTC",
        })
    assert response.status_code == 200
    assert [item["period_start"] for item in response.json()["observations"]] == ["2020-01-01", "2020-02-01"]
    assert response.json()["time_standard"] == "LST"


@pytest.mark.anyio
async def test_trend_endpoint_returns_descriptive_partial_year(app) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/relative-humidity/trend", params={
            "latitude": 0, "longitude": 0, "start_date": "2020-01-01", "end_date": "2020-01-03",
        })
    assert response.status_code == 200
    body = response.json()
    assert body["annual_summaries"][0]["eligibility_reasons"][0] == "partial_calendar_year"
    assert body["trend"]["result_level"] == "annual_summaries_only"
    assert body["methodology"]["annual_aggregation"] == "equal-weighted mean of valid monthly means"
    assert "available_images" not in body["annual_summaries"][0]
    assert "image_availability_percentage" not in body["annual_summaries"][0]


@pytest.mark.anyio
async def test_invalid_ranges_are_rejected_without_calling_power(app) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/relative-humidity", params={
            "latitude": 91, "longitude": 0, "start_date": "2020-01-01", "end_date": "2020-01-02",
        })
    assert response.status_code == 422


@pytest.mark.anyio
async def test_existing_ndvi_routes_remain_registered(app) -> None:
    paths = set(app.openapi()["paths"])
    assert "/api/v1/ndvi" in paths
    assert "/api/v1/ndvi/trend" in paths
