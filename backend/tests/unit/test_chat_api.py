import httpx
import pytest

from app.core.config import Settings
from app.main import create_app


class FakeChatService:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], dict | None]] = []

    def reply(self, messages: list[dict[str, str]], context: dict | None) -> str:
        self.calls.append((messages, context))
        return "The estimated trend is +0.05 °C per year."


@pytest.mark.anyio
async def test_chat_uses_the_supplied_analysis_context() -> None:
    service = FakeChatService()
    app = create_app(
        Settings(_env_file=None, ee_project_id="test", gemini_api_key="test-key"),
        chat_service=service,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/chat",
            json={
                "messages": [{"role": "user", "content": "What does this trend mean?"}],
                "context": {"variable": {"name": "Air temperature"}, "trend": {"slope": 0.05}},
            },
        )

    assert response.status_code == 200
    assert response.json() == {"answer": "The estimated trend is +0.05 °C per year."}
    assert service.calls[0][1]["trend"]["slope"] == 0.05


@pytest.mark.anyio
async def test_chat_reports_when_the_ai_service_is_not_configured() -> None:
    app = create_app(Settings(_env_file=None, ee_project_id="test", gemini_api_key=None))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v2/chat",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "chat_not_configured"
