import httpx
import pytest

from app.main import create_app


@pytest.mark.anyio
async def test_homepage_redirects_to_frontend() -> None:
    transport = httpx.ASGITransport(app=create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"

