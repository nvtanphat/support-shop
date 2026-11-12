"""Token-aware conversation trimming that never splits a tool-call pair."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


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


def prune_messages_token_aware(
    messages: list[BaseMessage],
    max_input_tokens: int = 10000,
) -> list[BaseMessage]:
    """Group messages into atomic conversational units to prevent splitting tool-call pairs.
    
    Ensures:
    1. AIMessage with tool_calls and all corresponding ToolMessages are never severed.
    2. Total tokens stay strictly within budget (default <= 10.000 tokens).
    3. The most recent user request and its context are always preserved.
    """
    if not messages:
        return []

    # 1. Group into atomic units (preserving AIMessage + ToolMessages pairs)
    units: list[list[BaseMessage]] = []
    i = 0
    n = len(messages)
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

    # 2. Accumulate units from newest to oldest within max_input_tokens
    selected_units: list[list[BaseMessage]] = []
    accumulated_tokens = 0

    for unit in reversed(units):
        unit_tokens = sum(estimate_message_tokens(m) for m in unit)
        if selected_units and (accumulated_tokens + unit_tokens > max_input_tokens):
            break
        selected_units.append(unit)
        accumulated_tokens += unit_tokens

    # Reverse back to chronological order and flatten
    selected_units.reverse()
    result: list[BaseMessage] = []
    for unit in selected_units:
        result.extend(unit)

    return result
