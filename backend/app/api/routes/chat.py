from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.services.chat_service import ChatServiceError


router = APIRouter(prefix="/api/v2", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=12)
    context: dict[str, Any] | None = None


class ChatService(Protocol):
    def reply(self, messages: list[dict[str, str]], context: dict[str, Any] | None) -> str: ...


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> dict[str, str]:
    service: ChatService | None = request.app.state.chat_service
    if service is None:
        raise HTTPException(
            status_code=503,
            detail={"reason": "chat_not_configured", "message": "Mission Scientist is not configured on this server."},
        )
    try:
        answer = await run_in_threadpool(
            service.reply,
            [message.model_dump() for message in body.messages],
            body.context,
        )
    except ChatServiceError as exc:
        raise HTTPException(status_code=502, detail={"reason": "chat_upstream_error", "message": str(exc)}) from exc
    return {"answer": answer}
