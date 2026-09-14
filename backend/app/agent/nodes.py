"""Graph nodes: input guard, the model call, and answer assembly."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agent.guardrails import screen_message
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.tools.registry import RETRIEVAL_TOOL_NAMES

logger = logging.getLogger(__name__)


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.type == "human":
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def make_guard_node(max_chars: int):
    """Screen the inbound message before it reaches the model."""

    def guard(state: AgentState) -> dict[str, Any]:
        result = screen_message(_last_human_text(state), max_chars=max_chars)
        if not result.blocked:
            return {"blocked": False, "block_reason": None}

        logger.warning("Blocked message from %s: %s", state.get("user_id"), result.reason)
        # The refusal is appended as an assistant turn so the thread history
        # stays coherent: the next turn sees that this request was declined.
        return {
            "blocked": True,
            "block_reason": result.reason,
            "messages": [AIMessage(content=result.message or "")],
        }

    return guard


def make_agent_node(model: BaseChatModel):
    """Call the tool-bound model with the system prompt prepended."""

    def agent(state: AgentState) -> dict[str, Any]:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = model.invoke(messages)
        return {"messages": [response]}

    return agent


def finalize(state: AgentState) -> dict[str, Any]:
    """Assemble the API response fields from the message history.

    Sources and tool calls are read out of the graph's own messages rather
    than out of the model's prose. If the model forgets to cite a section it
    retrieved, ``sources`` is still correct, and a confirmation id the model
    invented without calling a tool will not appear in ``tool_calls``.
    """
    requested: dict[str, dict[str, Any]] = {}
    tool_calls: list[dict[str, Any]] = []
    sources: list[str] = []

    for message in state.get("messages", []):
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                requested[call["id"]] = {"name": call["name"], "args": call["args"]}

        elif isinstance(message, ToolMessage):
            origin = requested.get(message.tool_call_id, {})
            name = origin.get("name") or message.name or "unknown"
            content = message.content if isinstance(message.content, str) else str(message.content)

            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = {"ok": False, "error": content}

            tool_calls.append(
                {
                    "tool": name,
                    "args": origin.get("args", {}),
                    "ok": bool(payload.get("ok")),
                    "result": payload.get("data", payload.get("error")),
                }
            )

            if name in RETRIEVAL_TOOL_NAMES and payload.get("ok"):
                for hit in payload.get("data", {}).get("results", []):
                    citation = hit.get("section_id")
                    if citation and citation not in sources:
                        sources.append(citation)

    return {"sources": sources, "tool_calls": tool_calls}
