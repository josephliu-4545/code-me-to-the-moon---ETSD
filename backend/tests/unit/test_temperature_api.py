from datetime import date

import httpx
import pytest

from app.core.operation_runner import BoundedOperationRunner
from app.main import create_app
from app.power.models import PowerParameter, PowerPayload
from app.services.temperature_service import TemperatureService


class FakeClient:
    def fetch_daily_point(self, query, parameter):
        assert parameter == PowerParameter.T2M
        return PowerPayload({"20200101": 25.0}, "C", -999, "LST", parameter)
    def fetch_monthly_point(self, query, parameter):
        return PowerPayload({"202001": 25.0, "202013": 25.0}, "C", -999, "LST", parameter)


@pytest.mark.anyio
async def test_temperature_endpoint_and_trend_metadata() -> None:
    runner = BoundedOperationRunner(1, "NASA POWER", "nasa-power-test")
    app = create_app(temperature_service=TemperatureService(FakeClient()), power_operation_runner=runner)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/temperature", params={"latitude": 16.8661, "longitude": 96.1951, "start_date": "2020-01-01", "end_date": "2020-01-02"})
            trend = await client.get("/api/v1/temperature/trend", params={"latitude": 16.8661, "longitude": 96.1951, "start_date": "2020-01-01", "end_date": "2020-01-02"})
    finally:
        runner.shutdown()
    assert response.status_code == 200
    assert response.json()["parameter"] == "T2M"
    assert response.json()["units"] == "°C"
    assert response.json()["time_standard"] == "LST"
    assert trend.status_code == 200
    assert trend.json()["methodology"]["annual_aggregation"] == "equal-weighted mean of valid monthly means"
    assert "slope_celsius_per_decade" in trend.json()["trend"]
    assert app.openapi()["paths"]["/api/v1/temperature"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("TemperatureResponse")
