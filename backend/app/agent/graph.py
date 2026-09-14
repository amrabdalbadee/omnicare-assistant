"""Assembly of the assistant's LangGraph workflow."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.nodes import finalize, make_agent_node, make_guard_node
from app.agent.state import AgentState
from app.tools.registry import TOOLS


def _route_after_guard(state: AgentState) -> str:
    return "finalize" if state.get("blocked") else "agent"


def _route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "finalize"


def build_graph(model: BaseChatModel, *, max_message_chars: int = 2000):
    """Compile the guard -> agent <-> tools -> finalize workflow.

    A blocked message short-circuits to ``finalize`` rather than raising, so
    a rejected turn still returns a well-formed response body with empty
    ``sources`` and ``tool_calls`` instead of an error status.
    """
    builder = StateGraph(AgentState)

    builder.add_node("guard", make_guard_node(max_message_chars))
    builder.add_node("agent", make_agent_node(model.bind_tools(TOOLS)))
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "guard")
    builder.add_conditional_edges(
        "guard", _route_after_guard, {"agent": "agent", "finalize": "finalize"}
    )
    builder.add_conditional_edges(
        "agent", _route_after_agent, {"tools": "tools", "finalize": "finalize"}
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("finalize", END)

    # Checkpointing keyed on user_id is what makes multi-turn claim filing
    # work: the agent can ask for a missing policy number and still have the
    # rest of the claim in hand on the next request.
    return builder.compile(checkpointer=MemorySaver())
