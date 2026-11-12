"""Node 4: verify_output - Deterministic safety and factual verification before customer sees response."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from shopagent.agent.state import AgentState
from shopagent.core.text import extract_text_content

_CLAUSE_REGEX = re.compile(r"\[(POL-[A-Z0-9\-]+)\]")
# A number with a business unit (money, days, percent...) is a factual claim that needs a source.
_CLAIM_NUMBER_REGEX = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(đ|₫|vnd|vnđ|k|ngày|giờ|phút|tháng|%)(?![\w])",
    re.IGNORECASE,
)
_ANY_NUMBER_REGEX = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")

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


_ESCALATION_CLAIM_PATTERNS = [
    r"(?:đã|sẽ)\s+(?:chuyển|kết\s+nối|gửi)\s+(?:thông\s+tin\s+cho|tới|qua)\s+(?:chuyên\s+viên|nhân\s+viên|tổng\s+đài)",
    r"(?:chuyên\s+viên|nhân\s+viên)\s+sẽ\s+liên\s+hệ",
    r"phiếu\s+hỗ\s+trợ\s+.*\s+(?:chuyển|gửi)",
]

_SAFE_DEFAULT_RESPONSE = (
    "Dạ hiện em chưa thể hoàn tất câu trả lời cho yêu cầu này. "
    "Quý khách vui lòng gửi lại yêu cầu hoặc bấm nút gặp nhân viên để được hỗ trợ trực tiếp ạ."
)

_UNMET_TOOL_RESPONSE = (
    "Dạ em chưa lấy được dữ liệu cần thiết trên hệ thống để trả lời chính xác yêu cầu này. "
    "Quý khách vui lòng thử lại sau ít phút hoặc bấm nút gặp nhân viên để được hỗ trợ trực tiếp ạ."
)

_PROPOSAL_TOOLS = ("propose_return", "propose_cancel_order")


def _degraded_response(state: AgentState) -> str:
    """Safe text for a turn that did not reach a verified final answer."""
    status = state.get("turn_status")
    executed = state.get("tool_calls", [])
    proposed = any(
        tc.get("tool") in _PROPOSAL_TOOLS and "error_code" not in (tc.get("result") or {})
        for tc in executed
    )
    if proposed:
        return (
            "Dạ em đã tạo đề xuất ở thẻ xác nhận bên dưới. Quý khách vui lòng kiểm tra thông tin "
            "trên thẻ trước khi bấm xác nhận ạ."
        )
    if status == "requirements_unmet":
        return _UNMET_TOOL_RESPONSE
    return _SAFE_DEFAULT_RESPONSE


def _normalize_number(raw: str) -> str:
    return re.sub(r"[.,]", "", raw)


def _claimed_numbers(content: str) -> set[str]:
    """Numbers the answer states together with a unit, normalised to plain digits (440k -> 440000)."""
    claimed: set[str] = set()
    for match in _CLAIM_NUMBER_REGEX.finditer(content):
        value = _normalize_number(match.group(1))
        claimed.add(value + "000" if match.group(2).lower() == "k" else value)
    return claimed


def _grounded_numbers(state: AgentState) -> set[str]:
    """Numbers present in sources the customer or the system really provided this conversation."""
    sources: list[str] = []
    for msg in state.get("messages", []):
        if isinstance(msg, (HumanMessage, ToolMessage)):
            sources.append(extract_text_content(msg.content))
    sources.extend(json.dumps(tc.get("result"), default=str, ensure_ascii=False) for tc in state.get("tool_calls", []))
    sources.append(json.dumps(state.get("dynamic_context") or {}, default=str, ensure_ascii=False))
    return {_normalize_number(n) for text in sources for n in _ANY_NUMBER_REGEX.findall(text)}


def verify_output_node(state: AgentState) -> dict[str, Any]:
    """Inspect the latest assistant message against hard business and security invariants."""
    status = state.get("turn_status")
    if status in ("requirements_unmet", "degraded"):
        return {
            "verified_output": _degraded_response(state),
            "error": f"TURN_NOT_COMPLETED: status={status}, unmet={state.get('unmet_requirements', [])}",
        }

    messages = state.get("messages", [])
    last_ai_msg: AIMessage | None = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_msg = msg
            break

    if last_ai_msg is None:
        return {"verified_output": _SAFE_DEFAULT_RESPONSE, "error": "TURN_NOT_COMPLETED: no assistant message"}
    if last_ai_msg.tool_calls:
        return {
            "verified_output": _degraded_response(state),
            "error": "TURN_NOT_COMPLETED: final assistant message still has pending tool calls",
        }

    content = extract_text_content(last_ai_msg.content)
    if not content.strip():
        return {"verified_output": _degraded_response(state), "error": "TURN_NOT_COMPLETED: empty assistant message"}

    retrieved_clauses = set(state.get("retrieved_clauses", []))
    tool_calls = state.get("tool_calls", [])
    escalation_done = any(
        tc.get("tool") == "escalate_to_human" and "ticket_code" in (tc.get("result") or {})
        for tc in tool_calls
    )

    violations = []

    # 1. Verify Policy Citations: Every [POL-...] must exist in retrieved_clauses
    cited_clauses = _CLAUSE_REGEX.findall(content)
    for c in cited_clauses:
        if c not in retrieved_clauses:
            violations.append(f"UNVERIFIED_CITATION: {c} not in retrieved clauses {retrieved_clauses}")

    # 2. Verify False Completion Claims (Invariant S5)
    content_lower = content.lower()
    for pat in _FALSE_COMPLETION_PATTERNS:
        if re.search(pat, content_lower):
            violations.append(f"FALSE_COMPLETION_CLAIM: matched '{pat}' without execution proof")
            break

    # 3. Verify Verbal Promises without Required Tool (Tool-first Enforcement)
    for pat in _ESCALATION_CLAIM_PATTERNS:
        if re.search(pat, content_lower) and not escalation_done:
            violations.append("VERBAL_PROMISE_WITHOUT_TOOL: Claimed human escalation without a created ticket")
            break

    # 3b. Every number with a unit must come from a tool result, the customer or the loaded context
    unsupported = sorted(_claimed_numbers(content) - _grounded_numbers(state))
    if unsupported:
        violations.append(f"UNSUPPORTED_NUMBER: {unsupported} not found in any tool result or customer message")

    # 4. Detect PII Leakage
    if _CARD_REGEX.search(content):
        violations.append("PII_LEAK: Payment card number detected in response")
    if _CCCD_REGEX.search(content):
        violations.append("PII_LEAK: Citizen ID detected in response")
    if _FULL_PHONE_REGEX.search(content):
        violations.append("PII_LEAK: Unmasked phone number detected in response")

    # If violations are detected, replace with safe compliant response
    if violations:
        safe_response = (
            "Dạ em chưa thể xác nhận chính xác nội dung này nên xin phép không đưa ra thông tin chưa kiểm chứng. "
            "Quý khách vui lòng thử lại hoặc bấm nút gặp nhân viên để được hỗ trợ trực tiếp ạ."
        )
        return {
            "verified_output": safe_response,
            "error": f"Verification failed: {'; '.join(violations)}",
        }

    return {"verified_output": content}
