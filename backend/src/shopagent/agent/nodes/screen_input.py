"""Node 2: screen_input - Screen user input for adversarial injection and canary leakage."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from shopagent.agent.state import AgentState

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"bỏ\s+qua\s+(mọi|tất\s+cả\s+)?(chỉ\s+dẫn|hướng\s+dẫn|yêu\s+cầu)",
    r"in\s+ra\s+(toàn\s+bộ\s+)?(system\s+prompt|prompt\s+gốc)",
    r"system\s+prompt",
    r"reveal\s+(your\s+)?instructions",
    r"you\s+are\s+now\s+in\s+dan\s+mode",
    r"jailbreak",
]


def screen_input_node(state: AgentState) -> dict[str, Any]:
    """Check user message for adversarial patterns. If flagged, stop and deflect."""
    messages = state.get("messages", [])
    if not messages:
        return {"screen_passed": True}

    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        return {"screen_passed": True}

    content = str(last_msg.content).lower()

    for pat in INJECTION_PATTERNS:
        if re.search(pat, content, re.IGNORECASE):
            deflection = AIMessage(
                content="Dạ em là trợ lý ShopLab. Em chỉ có thể hỗ trợ các thông tin liên quan đến đơn hàng và chính sách mua sắm tại cửa hàng. Quý khách cần hỗ trợ gì về đơn hàng ạ?"
            )
            return {
                "screen_passed": False,
                "verified_output": deflection.content,
                "messages": [deflection],
            }

    return {"screen_passed": True}
