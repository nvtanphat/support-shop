"""Node 4: verify_output - Deterministic safety and factual verification before customer sees response."""

from __future__ import annotations

import re
from typing import Any
from langchain_core.messages import AIMessage

from shopagent.agent.state import AgentState
from shopagent.core.text import extract_text_content

_CLAUSE_REGEX = re.compile(r"\[(POL-[A-Z0-9\-]+)\]")
_NUMBER_REGEX = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:đ|vnd|k|ngày|%)?\b", re.IGNORECASE)

# Patterns that claim completion of state-changing operations
_FALSE_COMPLETION_PATTERNS = [
    r"đã\s+hoàn\s+tiền",
    r"đã\s+hủy\s+(thành\s+công\s+)?đơn\s+hàng",
    r"đã\s+hủy\s+đơn\s+cho\s+bạn",
    r"đã\s+hủy\s+giúp\s+bạn",
    r"đơn\s+hàng\s+của\s+bạn\s+đã\s+được\s+hủy",
    r"tiền\s+đã\s+được\s+hoàn",
    r"đã\s+chuyển\s+tiền\s+hoàn",
    r"đã\s+xác\s+nhận\s+hủy\s+đơn",
    r"đã\s+xử\s+lý\s+hoàn\s+tiền\s+thành\s+công",
    r"đã\s+hoàn\s+tất\s+thủ\s+tục\s+hoàn\s+tiền",
    r"đã\s+đổi\s+hàng\s+thành\s+công",
]

# Sensitive PII patterns
_CARD_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
_CCCD_REGEX = re.compile(r"\b\d{12}\b")
_FULL_PHONE_REGEX = re.compile(r"\b0[35789]\d{8}\b")


def verify_output_node(state: AgentState) -> dict[str, Any]:
    """Inspect the latest assistant message against hard business and security invariants."""
    messages = state.get("messages", [])
    if not messages:
        return {"verified_output": ""}

    # Find the last AIMessage
    last_ai_msg: AIMessage | None = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_msg = msg
            break

    if not last_ai_msg or not last_ai_msg.content:
        return {"verified_output": ""}

    content = extract_text_content(last_ai_msg.content)
    retrieved_clauses = set(state.get("retrieved_clauses", []))

    violations = []

    # 1. Verify Policy Citations: Every [POL-...] must exist in retrieved_clauses
    cited_clauses = _CLAUSE_REGEX.findall(content)
    for c in cited_clauses:
        if c not in retrieved_clauses:
            violations.append(f"UNVERIFIED_CITATION: {c} not in retrieved clauses {retrieved_clauses}")

    # 2. Verify False Completion Claims (Invariant S5)
    # If no pending action was confirmed or executed in this turn, assistant CANNOT claim completion
    content_lower = content.lower()
    for pat in _FALSE_COMPLETION_PATTERNS:
        if re.search(pat, content_lower):
            violations.append(f"FALSE_COMPLETION_CLAIM: matched '{pat}' without execution proof")
            break

    # 3. Detect PII Leakage
    if _CARD_REGEX.search(content):
        violations.append("PII_LEAK: Payment card number detected in response")
    if _CCCD_REGEX.search(content):
        violations.append("PII_LEAK: Citizen ID detected in response")
    if _FULL_PHONE_REGEX.search(content):
        violations.append("PII_LEAK: Unmasked phone number detected in response")

    # If violations are detected, replace with safe compliant response
    if violations:
        safe_response = (
            "Dạ em đã ghi nhận thông tin và kiểm tra hệ thống. "
            "Để đảm bảo quyền lợi và bảo mật tài khoản tốt nhất cho quý khách, "
            "em xin phép hỗ trợ chuyển thông tin này tới chuyên viên hỗ trợ khách hàng để xử lý trực tiếp ạ."
        )
        return {
            "verified_output": safe_response,
            "error": f"Verification failed: {'; '.join(violations)}",
        }

    return {"verified_output": content}
