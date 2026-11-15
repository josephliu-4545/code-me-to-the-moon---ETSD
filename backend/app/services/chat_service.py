import json
from typing import Any

import httpx


SYSTEM_INSTRUCTIONS = """You are Mission Scientist, the assistant inside EarthLens.
Explain the supplied NASA-derived analysis accurately and in plain language.
Treat the analysis context as the source of truth. Never invent values, significance, causes, or certainty.
Distinguish trends from causes and grid-cell estimates from weather-station measurements.
Mention important exclusions, caveats, or limitations when relevant.
If context is missing, say that you can explain the app and its methods but need an investigation result to interpret specific findings.
Keep answers concise, helpful, and suitable for students, educators, journalists, and community groups."""


class ChatServiceError(RuntimeError):
    pass


class GeminiChatService:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def reply(self, messages: list[dict[str, str]], context: dict[str, Any] | None) -> str:
        context_text = json.dumps(context, ensure_ascii=False, separators=(",", ":")) if context else "No investigation result is currently available."
        contents = [
            {
                "role": "user" if message["role"] == "user" else "model",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
        ]
        contents[0]["parts"][0]["text"] = (
            f"Assistant instructions:\n{SYSTEM_INSTRUCTIONS}\n\n"
            f"Current investigation context:\n{context_text}\n\n"
            f"User question:\n{contents[0]['parts'][0]['text']}"
        )
        payload = {
            "contents": contents,
        }
        try:
            response = self._request(payload)
        except httpx.HTTPStatusError as exc:
            message = "Request rejected by Gemini."
            try:
                supplied = exc.response.json().get("error", {}).get("message")
                if isinstance(supplied, str) and supplied.strip():
                    message = " ".join(supplied.split())[:500]
            except (ValueError, AttributeError):
                pass
            raise ChatServiceError(
                f"Gemini returned {exc.response.status_code}: {message}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ChatServiceError(
                f"Gemini did not answer within {self.timeout_seconds:g} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatServiceError(f"Could not reach Gemini: {type(exc).__name__}.") from exc

        body = response.json()
        for candidate in body.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text"):
                    return str(part["text"])
        raise ChatServiceError("The AI service returned no answer.")

    def _request(self, payload: dict[str, Any]) -> httpx.Response:
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
            return response
