from datetime import date
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app
from app.schemas.trend import NDVITrendResponse


class FakeTrendService:
    def analyze(self, query: Any) -> NDVITrendResponse:
        return NDVITrendResponse.model_validate(
            {
                "variable": "NDVI",
                "dataset": "NASA MODIS MOD13Q1.061",
                "units": "NDVI units",
                "location": {"latitude": query.latitude, "longitude": query.longitude, "radius_km": query.radius_km},
                "period": {"start": query.start_date, "end": query.end_date},
                "observation_count": 0,
                "eligible_annual_observation_count": 0,
                "annual_summaries": [],
                "trend": {
                    "result_level": "annual_summaries_only",
                    "eligible_years": [],
                    "excluded_years": [],
                    "missing_years": [],
                    "theil_sen": None,
                    "serial_dependence": None,
                    "mann_kendall": None,
                    "slope_unavailable_reason": "At least 3 eligible annual observations are required",
                    "significance_unavailable_reason": "At least 3 eligible annual observations are required"
                },
                "coverage_definitions": {"valid_observations": "Quality-filtered regional values"},
                "methodology": {"thresholds_are_universal_standards": False},
                "limitations": ["A nonsignificant autocorrelation diagnostic does not prove independence."]
            }
        )


@pytest.mark.anyio
async def test_trend_endpoint_is_additive_and_returns_methodology() -> None:
    app = create_app(
        settings=Settings(ee_project_id="unused"),
        ndvi_trend_service=FakeTrendService(),
    )
    transport = httpx.ASGITransport(app=app)
    params = {
        "latitude": 16.8661,
        "longitude": 96.1951,
        "start_date": "2020-01-01",
        "end_date": "2021-01-01",
        "radius_km": 5,
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi/trend", params=params)

    assert response.status_code == 200
    assert response.json()["trend"]["result_level"] == "annual_summaries_only"
    assert response.json()["methodology"]["thresholds_are_universal_standards"] is False
    paths = app.openapi()["paths"]
    assert "/api/v1/ndvi" in paths
    assert "/api/v1/ndvi/trend" in paths


@pytest.mark.anyio
async def test_trend_endpoint_preserves_validation_rules() -> None:
    app = create_app(
        settings=Settings(ee_project_id="unused"),
        ndvi_trend_service=FakeTrendService(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/ndvi/trend",
            params={
                "latitude": 91,
                "longitude": 0,
                "start_date": "2020-01-01",
                "end_date": "2021-01-01",
            },
        )
    assert response.status_code == 422

