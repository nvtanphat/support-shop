"""Claim-to-evidence validation for the assistant's final answer.

Evidence is only what a tool returned successfully (this turn or earlier in the conversation)
plus what the customer just said. A failed call, a refusal or an old customer message never
backs a claim. Each supported claim is traced to the tool that produced it so a wrong answer
can be audited.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage

from shopagent.agent.state import AgentState
from shopagent.agent.tool_requirements import ORDER_CODE_RE, ToolOutcome, classify_result
from shopagent.core.text import extract_text_content

# A number with a business unit (money, days, percent...) is a factual claim.
_CLAIM_NUMBER_RE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(đ|₫|vnd|vnđ|k|ngày|giờ|phút|tháng|%)(?![\w])",
    re.IGNORECASE,
)
_ANY_NUMBER_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")

_REFUND_DONE_RE = re.compile(
    r"đã\s+hoàn\s+tiền|tiền\s+đã\s+được\s+hoàn|đã\s+chuyển\s+tiền\s+hoàn"
    r"|đã\s+xử\s+lý\s+hoàn\s+tiền\s+thành\s+công|đã\s+hoàn\s+tất\s+thủ\s+tục\s+hoàn\s+tiền"
)
_CANCEL_DONE_RE = re.compile(
    r"đã\s+hủy\s+(?:thành\s+công\s+)?đơn|đã\s+hủy\s+giúp|đơn\s+hàng\s+của\s+bạn\s+đã\s+được\s+hủy|đã\s+xác\s+nhận\s+hủy\s+đơn"
)
_EXCHANGE_DONE_RE = re.compile(r"đã\s+đổi\s+hàng\s+thành\s+công")


@dataclass(frozen=True)
class Violation:
    kind: str
    claim: str
    detail: str


@dataclass
class Evidence:
    """Successful tool facts, indexed for claim checks."""

    numbers: dict[str, str] = field(default_factory=dict)  # normalised number -> source tool
    order_codes: dict[str, str] = field(default_factory=dict)
    refund_succeeded_by: str | None = None
    order_cancelled_by: str | None = None


def normalize_number(raw: str) -> str:
    return re.sub(r"[.,]", "", raw)


def _walk(value: Any):  # type: ignore[no-untyped-def]
    yield value
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)


def _absorb(evidence: Evidence, tool: str, result: Any) -> None:
    text = json.dumps(result, default=str, ensure_ascii=False)
    for raw in _ANY_NUMBER_RE.findall(text):
        evidence.numbers.setdefault(normalize_number(raw), tool)
    for match in ORDER_CODE_RE.finditer(text):
        evidence.order_codes.setdefault(match.group(0).upper(), tool)
    for node in _walk(result):
        if not isinstance(node, dict):
            continue
        if node.get("case_type") == "refund" and node.get("status") == "succeeded":
            evidence.refund_succeeded_by = tool
        if node.get("status") == "cancelled" and (node.get("order_code") or node.get("code")):
            evidence.order_cancelled_by = tool


def collect_evidence(state: AgentState) -> Evidence:
    evidence = Evidence()
    for msg in state.get("messages", []):
        if not isinstance(msg, ToolMessage):
            continue
        try:
            result = json.loads(extract_text_content(msg.content))
        except ValueError:
            continue
        if classify_result(result) is ToolOutcome.SUCCEEDED:
            _absorb(evidence, msg.name or "tool", result)
    for call in state.get("tool_calls", []):
        if classify_result(call.get("result")) is ToolOutcome.SUCCEEDED:
            _absorb(evidence, str(call.get("tool")), call.get("result"))
    for order in (state.get("dynamic_context") or {}).get("recent_orders") or []:
        if order.get("code"):
            evidence.order_codes.setdefault(str(order["code"]).upper(), "recent_orders")
    return evidence


def _latest_customer_text(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return extract_text_content(msg.content)
    return ""


def claimed_numbers(content: str) -> dict[str, str]:
    """Numbers stated with a unit, normalised to plain digits (440k -> 440000), mapped to the claim text."""
    claimed: dict[str, str] = {}
    for match in _CLAIM_NUMBER_RE.finditer(content):
        value = normalize_number(match.group(1))
        if match.group(2).lower() == "k":
            value += "000"
        claimed.setdefault(value, match.group(0).strip())
    return claimed


def check_claims(content: str, state: AgentState) -> tuple[list[Violation], dict[str, str]]:
    """Return violations and, for each supported claim, the source that backs it."""
    evidence = collect_evidence(state)
    customer_text = _latest_customer_text(state)
    customer_numbers = {normalize_number(n) for n in _ANY_NUMBER_RE.findall(customer_text)}
    customer_orders = {m.group(0).upper() for m in ORDER_CODE_RE.finditer(customer_text)}
    violations: list[Violation] = []
    supported: dict[str, str] = {}
    lowered = content.lower()

    for value, claim in claimed_numbers(content).items():
        if value in evidence.numbers:
            supported[claim] = evidence.numbers[value]
        elif value in customer_numbers:
            supported[claim] = "customer_message"
        else:
            violations.append(Violation("UNSUPPORTED_NUMBER", claim, "no successful tool result contains this value"))

    for match in ORDER_CODE_RE.finditer(content):
        code = match.group(0).upper()
        if code in evidence.order_codes:
            supported[code] = evidence.order_codes[code]
        elif code not in customer_orders:
            violations.append(Violation("UNSUPPORTED_ORDER", code, "order was not looked up or mentioned by the customer"))

    if _REFUND_DONE_RE.search(lowered) and evidence.refund_succeeded_by is None:
        violations.append(Violation("FALSE_COMPLETION_CLAIM", "refund completed", "no refund with status succeeded in tool results"))
    if _CANCEL_DONE_RE.search(lowered) and evidence.order_cancelled_by is None:
        violations.append(Violation("FALSE_COMPLETION_CLAIM", "order cancelled", "no order with status cancelled in tool results"))
    if _EXCHANGE_DONE_RE.search(lowered):
        violations.append(Violation("FALSE_COMPLETION_CLAIM", "exchange completed", "no tool reports a completed exchange"))
    return violations, supported
