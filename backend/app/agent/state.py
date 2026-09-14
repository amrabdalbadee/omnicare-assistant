"""Graph state for the assistant."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State threaded through the graph.

    ``messages`` accumulates across turns via the ``add_messages`` reducer so
    a claim can be filled in over several exchanges. The remaining keys have
    no reducer and are supplied fresh on every invocation, which resets them
    per turn -- ``sources`` must describe this answer, not every answer the
    thread has ever produced.
    """

    user_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    sources: list[str]
    tool_calls: list[dict[str, Any]]
    blocked: bool
    block_reason: str | None
