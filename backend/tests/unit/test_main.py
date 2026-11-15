import httpx
import pytest

from app.main import create_app


@pytest.mark.anyio
async def test_homepage_reports_application_status() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "EarthLens API",
        "version": "0.1.0",
        "status": "ok",
    }

