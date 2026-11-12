"""LangGraph Agent State definition."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from shopagent.core.principal import Principal


class AgentState(TypedDict, total=False):
    """Shared state for the 5-node LangGraph agent graph."""

    conversation_id: str
    turn_id: str | None
    request_id: str | None
    messages: Annotated[list[BaseMessage], add_messages]
    principal: Principal
    clock: datetime
    dynamic_context: dict[str, Any]
    retrieved_clauses: list[str]
    tool_calls: list[dict[str, Any]]
    pending_action: dict[str, Any] | None
    events: list[dict[str, Any]]
    screen_passed: bool
    verified_output: str | None
    # How the agent loop ended: completed | synthesized | requirements_unmet | degraded.
    turn_status: str
    unmet_requirements: list[str]
    error: str | None
