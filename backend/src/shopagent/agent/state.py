"""LangGraph Agent State definition."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from shopagent.core.principal import Principal


class AgentState(TypedDict, total=False):
    """Shared state for the 5-node LangGraph agent graph."""

    conversation_id: str
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
    error: str | None
