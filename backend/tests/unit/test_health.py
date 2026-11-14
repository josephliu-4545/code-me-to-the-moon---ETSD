import httpx
import pytest

from app.core.config import Settings
from app.core.earth_engine import EarthEngineManager
from app.core.operation_runner import OperationTimeoutError
from app.main import create_app


class SuccessfulEarthEngine:
    def Initialize(self, *, project: str) -> None:
        pass


class FailingEarthEngine:
    def Initialize(self, *, project: str) -> None:
        raise RuntimeError("token at C:/private/credentials")


class TimeoutRunner:
    async def run(self, operation: object, timeout_seconds: float) -> object:
        raise OperationTimeoutError()

    def shutdown(self) -> None:
        pass


@pytest.mark.anyio
async def test_health_reports_ready_earth_engine() -> None:
    manager = EarthEngineManager("project-id", SuccessfulEarthEngine())
    transport = httpx.ASGITransport(app=create_app(ee_manager=manager))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "earth_engine": "ready"}


@pytest.mark.anyio
async def test_health_sanitizes_initialization_failure() -> None:
    manager = EarthEngineManager("project-id", FailingEarthEngine())
    transport = httpx.ASGITransport(app=create_app(ee_manager=manager))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "earth_engine": "failed"}
    assert "private" not in response.text


@pytest.mark.anyio
async def test_health_reports_missing_configuration_without_project_value() -> None:
    settings = Settings(ee_project_id=None)
    transport = httpx.ASGITransport(app=create_app(settings=settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "earth_engine": "failed"}


@pytest.mark.anyio
async def test_health_handles_bounded_initialization_timeout() -> None:
    manager = EarthEngineManager("project-id", SuccessfulEarthEngine())
    transport = httpx.ASGITransport(
        app=create_app(ee_manager=manager, operation_runner=TimeoutRunner())
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "earth_engine": "failed"}

