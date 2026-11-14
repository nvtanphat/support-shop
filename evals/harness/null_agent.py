"""Null Agent for evaluation sanity check."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class NullAgent:
    """Agent that takes no actions, makes no tool calls, and emits blank or generic refusal.

    Required to fail all state-change scenarios.
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def step(
        self,
        conversation_id: str,
        user_message: str,
        dialogue_history: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        """Respond with generic idle message without invoking any tools or proposing actions.

        Returns:
            (assistant_message: str, tool_calls: list[dict], pending_action: dict | None)
        """
        return (
            "Dạ em là trợ lý ShopLab. Hiện em chưa thể hỗ trợ yêu cầu này của quý khách.",
            [],
            None,
        )
