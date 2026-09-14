"""Request and response models for the public API."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    model_config = {"extra": "forbid"}

    user_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            pattern=r"^[A-Za-z0-9_\-]+$",
            description="Stable per-user id; also used as the conversation thread key.",
            examples=["usr_123"],
        ),
    ]
    message: Annotated[
        str,
        Field(min_length=1, max_length=4000, examples=["Is a burst pipe covered?"])
    ]


class ToolCallRecord(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    result: Any = None


class ChatResponse(BaseModel):
    response: str
    sources: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "healthy"
