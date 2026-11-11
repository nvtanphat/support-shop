"""LangGraph StateGraph definition for Shop Support Agent."""

from __future__ import annotations

from typing import Any
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from shopagent.agent.nodes.agent import agent_node
from shopagent.agent.nodes.load_context import load_context_node
from shopagent.agent.nodes.persist_emit import persist_emit_node
from shopagent.agent.nodes.screen_input import screen_input_node
from shopagent.agent.nodes.verify_output import verify_output_node
from shopagent.agent.state import AgentState


def route_after_screen(state: AgentState) -> str:
    """Route to agent reasoning or deflect straight to persist_emit if screening failed."""
    if state.get("screen_passed", True):
        return "agent"
    return "persist_emit"


def build_agent_graph(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    """Construct and compile the 5-node Shop Support Agent graph."""
    builder = StateGraph(AgentState)

    # Add the 5 official nodes
    builder.add_node("load_context", load_context_node)
    builder.add_node("screen_input", screen_input_node)
    builder.add_node("agent", agent_node)
    builder.add_node("verify_output", verify_output_node)
    builder.add_node("persist_emit", persist_emit_node)

    # Wire edges
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "screen_input")
    builder.add_conditional_edges(
        "screen_input",
        route_after_screen,
        {
            "agent": "agent",
            "persist_emit": "persist_emit",
        },
    )
    builder.add_edge("agent", "verify_output")
    builder.add_edge("verify_output", "persist_emit")
    builder.add_edge("persist_emit", END)

    if checkpointer is None:
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# Default singleton instance
_compiled_graph: Any = None


def get_agent_graph(checkpointer: BaseCheckpointSaver | None = None) -> Any:
    """Get or instantiate compiled agent graph."""
    global _compiled_graph
    if _compiled_graph is None or checkpointer is not None:
        _compiled_graph = build_agent_graph(checkpointer=checkpointer)
    return _compiled_graph
