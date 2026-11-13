"""Node 2: screen_input - Screen user input for adversarial injection and canary leakage."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from shopagent.agent.state import AgentState
from shopagent.core.security import mask_sensitive_numbers

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"bỏ\s+qua\s+(?:(?:mọi|tất\s+cả)\s+)?(?:chỉ\s+dẫn|hướng\s+dẫn|yêu\s+cầu)",
    r"in\s+ra\s+(toàn\s+bộ\s+)?(system\s+prompt|prompt\s+gốc)",
    r"system\s+prompt",
    r"reveal\s+(your\s+)?instructions",
    r"you\s+are\s+now\s+in\s+dan\s+mode",
    r"jailbreak",
    r"developer\s+mode|chế\s+độ\s+(?:nhà\s+phát\s+triển|dev)",
    r"(?:quên|bỏ)\s+(?:hết|toàn\s+bộ)\s+(?:những\s+)?(?:gì|chỉ\s+dẫn|hướng\s+dẫn)\s+(?:trước|đã)",
    r"(?:tiết\s+lộ|cho\s+(?:tôi|mình)\s+xem|hiển\s+thị)\s+(?:prompt|chỉ\s+dẫn|hướng\s+dẫn)\s+(?:hệ\s+thống|gốc|ban\s+đầu)",
    r"prompt\s+hệ\s+thống",
    r"đóng\s+vai\s+(?:là\s+)?(?:một\s+)?(?:ai\s+không\s+bị|không\s+bị\s+giới\s+hạn)",
]


def screen_input_node(state: AgentState) -> dict[str, Any]:
    """Check user message for adversarial patterns. If flagged, stop and deflect."""
    messages = state.get("messages", [])
    if not messages:
        return {"screen_passed": True}

    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        return {"screen_passed": True}

    # A card or citizen ID number typed into the chat is replaced (same message id) before the model sees it
    # and before the turn is persisted or checkpointed: it must not be stored, nor sent to the LLM provider.
    replaced: list[HumanMessage] = []
    if isinstance(last_msg.content, str):
        masked = mask_sensitive_numbers(last_msg.content)
        if masked != last_msg.content:
            replaced = [HumanMessage(content=masked, id=last_msg.id)]

    content = str(replaced[0].content if replaced else last_msg.content).lower()

    for pat in INJECTION_PATTERNS:
        if re.search(pat, content, re.IGNORECASE):
            deflection = AIMessage(
                content="Dạ em là trợ lý ShopLab. Em chỉ có thể hỗ trợ các thông tin liên quan đến đơn hàng và chính sách mua sắm tại cửa hàng. Quý khách cần hỗ trợ gì về đơn hàng ạ?"
            )
            return {
                "screen_passed": False,
                "verified_output": deflection.content,
                "messages": [*replaced, deflection],
            }

    return {"screen_passed": True, "messages": replaced} if replaced else {"screen_passed": True}
