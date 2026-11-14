"""Tool registry providing dynamically filtered tools based on Principal."""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.tools.definitions import create_tools
from shopagent.core.principal import Principal


class ToolRegistry:
    """Registry that exposes tools dynamically according to caller's Principal and session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def get_tools(
        self,
        principal: Principal,
        conversation_id: uuid.UUID,
        retrieved_clauses: list[str] | None = None,
        proposed_actions_out: list[dict[str, Any]] | None = None,
    ) -> list[StructuredTool]:
        """Return authorized tools for this principal."""
        return create_tools(
            session=self.session,
            principal=principal,
            conversation_id=conversation_id,
            retrieved_clauses=retrieved_clauses,
            proposed_actions_out=proposed_actions_out,
        )
