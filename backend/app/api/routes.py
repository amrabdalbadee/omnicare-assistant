"""HTTP surface: chat and health."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage

from app.api.schemas import ChatRequest, ChatResponse, HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    graph = request.app.state.graph
    settings = request.app.state.settings

    try:
        final_state = await graph.ainvoke(
            {
                "user_id": payload.user_id,
                "messages": [HumanMessage(content=payload.message)],
                # Reset per-turn fields; only `messages` accumulates.
                "sources": [],
                "tool_calls": [],
                "blocked": False,
                "block_reason": None,
            },
            config={
                "configurable": {"thread_id": payload.user_id},
                "recursion_limit": settings.agent_recursion_limit,
            },
        )
    except Exception as exc:
        logger.exception("Agent run failed for user %s", payload.user_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The assistant could not complete this request: {exc}",
        ) from exc

    answer = ""
    for message in reversed(final_state.get("messages", [])):
        if isinstance(message, AIMessage) and not message.tool_calls:
            answer = message.content if isinstance(message.content, str) else str(message.content)
            break

    return ChatResponse(
        response=answer,
        sources=final_state.get("sources", []),
        tool_calls=final_state.get("tool_calls", []),
    )
