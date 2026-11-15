import json

import httpx

from app.services.chat_service import ChatServiceError, GeminiChatService
from app.core.config import Settings


def test_new_projects_use_the_current_free_tier_model() -> None:
    assert Settings(_env_file=None).gemini_model == "gemini-3.5-flash-lite"


def test_gemini_chat_sends_grounded_context_and_reads_the_answer() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-goog-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "The trend is an estimate, not proof of a cause."}]}}]},
        )

    service = GeminiChatService(
        api_key="free-key",
        model="gemini-3.5-flash-lite",
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )
    answer = service.reply(
        [{"role": "user", "content": "What does this mean?"}],
        {"trend": {"slope": 0.05}},
    )

    assert answer == "The trend is an estimate, not proof of a cause."
    assert captured["key"] == "free-key"
    assert "gemini-3.5-flash-lite:generateContent" in captured["url"]
    prompt = captured["body"]["contents"][0]["parts"][0]["text"]
    assert "system_instruction" not in captured["body"]
    assert "You are Mission Scientist" in prompt
    assert '"slope":0.05' in prompt
    assert "generationConfig" not in captured["body"]


def test_gemini_chat_preserves_safe_upstream_error_details() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            429,
            request=request,
            json={"error": {"message": "Free-tier quota exceeded. Try again later."}},
        )
    )
    service = GeminiChatService("free-key", "gemini-3.5-flash-lite", 10, transport)

    try:
        service.reply([{"role": "user", "content": "Hello"}], None)
    except ChatServiceError as exc:
        assert str(exc) == "Gemini returned 429: Free-tier quota exceeded. Try again later."
    else:
        raise AssertionError("Expected ChatServiceError")
