from datetime import date
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.earth_engine import EarthEngineInitializationError
from app.core.operation_runner import OperationBusyError, OperationTimeoutError
from app.main import create_app
from app.schemas.ndvi import NDVILocation, NDVIPeriod, NDVIResponse
from app.services.modis_service import EarthEngineRetrievalError


VALID_PARAMS = {
    "latitude": 16.8661,
    "longitude": 96.1951,
    "start_date": "2020-01-01",
    "end_date": "2021-01-01",
    "radius_km": 5,
}


class FakeService:
    def __init__(self, result: NDVIResponse | None = None, error: Exception | None = None) -> None:
        self.result = result or NDVIResponse(
            location=NDVILocation(latitude=16.8661, longitude=96.1951, radius_km=5),
            period=NDVIPeriod(start=date(2020, 1, 1), end=date(2021, 1, 1)),
            observation_count=0,
            observations=[],
        )
        self.error = error
        self.queries: list[Any] = []

    def fetch_ndvi(self, query: Any) -> NDVIResponse:
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.result


class RaisingRunner:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def run(self, operation: Any, timeout_seconds: float) -> Any:
        raise self.error

    def shutdown(self) -> None:
        pass


def make_transport(service: FakeService, runner: Any | None = None) -> httpx.ASGITransport:
    settings = Settings(ee_project_id="unused-for-mocked-api")
    return httpx.ASGITransport(
        app=create_app(settings=settings, modis_service=service, operation_runner=runner)
    )


@pytest.mark.anyio
async def test_ndvi_returns_structured_empty_response() -> None:
    service = FakeService()
    transport = make_transport(service)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=VALID_PARAMS)

    assert response.status_code == 200
    assert response.json() == {
        "variable": "NDVI",
        "dataset": "NASA MODIS MOD13Q1.061",
        "units": "NDVI units",
        "location": {"latitude": 16.8661, "longitude": 96.1951, "radius_km": 5.0},
        "period": {"start": "2020-01-01", "end": "2021-01-01"},
        "observation_count": 0,
        "observations": [],
    }
    assert service.queries[0].end_date == date(2021, 1, 1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [("latitude", 91), ("latitude", -91), ("longitude", 181), ("longitude", -181)],
)
async def test_ndvi_rejects_invalid_coordinates(field: str, value: float) -> None:
    params = {**VALID_PARAMS, field: value}
    transport = make_transport(FakeService())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=params)

    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2021-01-01", "2021-01-01"),
        ("2021-01-02", "2021-01-01"),
        ("2020-01-01", "2030-01-02"),
    ],
)
async def test_ndvi_rejects_invalid_date_ranges(start: str, end: str) -> None:
    params = {**VALID_PARAMS, "start_date": start, "end_date": end}
    transport = make_transport(FakeService())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=params)

    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("start", "end"),
    [("2020-01-01", "2030-01-01"), ("2020-02-29", "2030-02-28")],
)
async def test_ndvi_accepts_ten_year_calendar_boundaries(start: str, end: str) -> None:
    params = {**VALID_PARAMS, "start_date": start, "end_date": end}
    transport = make_transport(FakeService())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=params)

    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("radius", [0, -1, 100.1])
async def test_ndvi_rejects_invalid_radius(radius: float) -> None:
    params = {**VALID_PARAMS, "radius_km": radius}
    transport = make_transport(FakeService())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=params)

    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("runner_error", "expected_status"),
    [(OperationBusyError(), 503), (OperationTimeoutError(), 504)],
)
async def test_ndvi_maps_runner_failures(runner_error: Exception, expected_status: int) -> None:
    transport = make_transport(FakeService(), RaisingRunner(runner_error))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=VALID_PARAMS)

    assert response.status_code == expected_status


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("service_error", "expected_status"),
    [
        (EarthEngineInitializationError("private path"), 503),
        (EarthEngineRetrievalError("private remote response"), 502),
    ],
)
async def test_ndvi_sanitizes_earth_engine_failures(
    service_error: Exception,
    expected_status: int,
) -> None:
    transport = make_transport(FakeService(error=service_error))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ndvi", params=VALID_PARAMS)

    assert response.status_code == expected_status
    assert "private" not in response.text

