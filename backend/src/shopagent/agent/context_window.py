"""Token-aware conversation trimming that never splits a tool-call pair."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def estimate_message_tokens(msg: BaseMessage) -> int:
    """Approximate token count for a single message."""
    content = str(msg.content or "")
    tokens = max(1, len(content) // 3)
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        try:
            tokens += len(json.dumps(msg.tool_calls)) // 3
        except Exception:
            tokens += 50
    return tokens + 4  # overhead per message


def estimate_text_tokens(text: str) -> int:
    return max(1, len(text) // 3)


def _group_units(messages: list[BaseMessage]) -> list[list[BaseMessage]]:
    """Atomic units: an AIMessage with tool calls stays together with its ToolMessages."""
    units: list[list[BaseMessage]] = []
    i, n = 0, len(messages)
    while i < n:
        msg = messages[i]
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            unit: list[BaseMessage] = [msg]
            i += 1
            while i < n and isinstance(messages[i], ToolMessage):
                unit.append(messages[i])
                i += 1
            units.append(unit)
        else:
            units.append([msg])
            i += 1
    return units


def prune_messages_token_aware(
    messages: list[BaseMessage],
    max_input_tokens: int = 10000,
    reserved_tokens: int = 0,
) -> list[BaseMessage]:
    """Trim old history to the token budget without ever breaking a tool-call pair.

    `reserved_tokens` is what the system prompt and tool schemas already use. The current turn (the
    latest customer message and everything after it) is always kept whole, whatever its size: dropping
    the question or a fresh tool result would make the model answer blind. Only older history is trimmed.
    """
    if not messages:
        return []
    units = _group_units(messages)
    last_human_unit = max((i for i, u in enumerate(units) if isinstance(u[0], HumanMessage)), default=0)
    current_turn = units[last_human_unit:]
    history = units[:last_human_unit]

    budget = max_input_tokens - reserved_tokens - sum(estimate_message_tokens(m) for u in current_turn for m in u)
    kept: list[list[BaseMessage]] = []
    for unit in reversed(history):
        cost = sum(estimate_message_tokens(m) for m in unit)
        if cost > budget:
            break
        kept.append(unit)
        budget -= cost
    kept.reverse()
    # A window must open with a customer message: an assistant answer without its question confuses the model.
    while kept and not isinstance(kept[0][0], HumanMessage):
        kept.pop(0)
    return [m for unit in (*kept, *current_turn) for m in unit]
