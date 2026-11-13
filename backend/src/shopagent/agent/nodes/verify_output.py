"""Node 4: verify_output - Deterministic safety and factual verification before customer sees response."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage

from shopagent.agent.grounding import check_claims
from shopagent.agent.state import AgentState
from shopagent.core.text import extract_text_content

logger = logging.getLogger(__name__)

_CLAUSE_REGEX = re.compile(r"\[(POL-[A-Z0-9\-]+)\]")
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
    ticket = next(
        (
            tc["result"]["ticket_code"]
            for tc in executed
            if tc.get("tool") == "escalate_to_human" and "ticket_code" in (tc.get("result") or {})
        ),
        None,
    )
    if ticket:
        # The ticket exists in the database even though the model could not phrase the answer.
        return (
            f"Dạ em đã tạo phiếu hỗ trợ {ticket} và chuyển yêu cầu của quý khách tới chuyên viên chăm sóc khách hàng. "
            "Chuyên viên sẽ liên hệ lại với quý khách trong vòng 30 phút ạ."
        )
    if status == "requirements_unmet":
        return _UNMET_TOOL_RESPONSE
    return _SAFE_DEFAULT_RESPONSE


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

    # 3. Verify Verbal Promises without Required Tool (Tool-first Enforcement)
    for pat in _ESCALATION_CLAIM_PATTERNS:
        if re.search(pat, content.lower()) and not escalation_done:
            violations.append("VERBAL_PROMISE_WITHOUT_TOOL: Claimed human escalation without a created ticket")
            break

    # 2. Claim-to-evidence: numbers, order identity and completion claims need successful tool evidence
    claim_violations, supported_claims = check_claims(content, state)
    violations.extend(f"{v.kind}: {v.claim} ({v.detail})" for v in claim_violations)

    # 4. Detect PII Leakage
    if _CARD_REGEX.search(content):
        violations.append("PII_LEAK: Payment card number detected in response")
    if _CCCD_REGEX.search(content):
        violations.append("PII_LEAK: Citizen ID detected in response")
    if _FULL_PHONE_REGEX.search(content):
        violations.append("PII_LEAK: Unmasked phone number detected in response")

    # If violations are detected, replace with safe compliant response
    if violations:
        logger.warning("Câu trả lời bị chặn ở bước kiểm tra đầu ra: %s | nội dung: %.300s", "; ".join(violations), content)
        safe_response = (
            "Dạ em chưa thể xác nhận chính xác nội dung này nên xin phép không đưa ra thông tin chưa kiểm chứng. "
            "Quý khách vui lòng thử lại hoặc bấm nút gặp nhân viên để được hỗ trợ trực tiếp ạ."
        )
        return {
            "verified_output": safe_response,
            "error": f"Verification failed: {'; '.join(violations)}",
        }

    return {"verified_output": content, "claim_evidence": supported_claims}
