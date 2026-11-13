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
# The reply points the customer at a confirmation card. The card only exists once propose_* succeeded, so a reply
# that promises one ("mình sẽ tạo đề xuất... bấm Xác nhận trên thẻ bên dưới") without the call leaves the customer
# with instructions and nothing to click. Any instruction to press "Xác nhận" counts, wherever it says the button is:
# "bấm nút Xác nhận để hoàn tất" slipped past a pattern that required "trên thẻ".
_PROPOSAL_CARD_RE = re.compile(
    r"thẻ\s+(?:hành\s+động|đề\s+xuất|xác\s+nhận)"
    r"|(?:nhấn|bấm|chọn)\s+(?:vào\s+)?(?:nút\s+)?[*\"“'\s]*xác\s+nhận"
    r"|(?:đã|em\s+đã|mình\s+đã|tôi\s+đã)\s+(?:tạo|lập)\s+(?:một\s+)?đề\s+xuất"
    r"|vui\s+lòng\s+(?:kiểm\s+tra[^.\n]{0,40}?\s)?xác\s+nhận\s+(?:lại\s+)?(?:yêu\s+cầu|đề\s+xuất)"
)
# A proposal is not yet a return request: the request exists only after the customer confirms on the card. Saying
# "đã tạo yêu cầu trả hàng" for a proposal tells the customer a pending action is done.
_RETURN_CREATED_RE = re.compile(
    r"(?:đã|em\s+đã|mình\s+đã|tôi\s+đã)\s+(?:tạo|lập|gửi|ghi\s+nhận)\s+(?:một\s+)?yêu\s+cầu\s+(?:trả|hoàn|đổi)"
    r"|yêu\s+cầu\s+(?:trả|hoàn|đổi)[^.\n]{0,40}?\s+đã\s+(?:được\s+)?(?:tạo|ghi\s+nhận|gửi)"
)
_CITATION_RE = re.compile(r"\[?(POL-[A-Z0-9-]+)\]?")
_PROPOSAL_TOOLS = ("propose_return", "propose_cancel_order")


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
    return_exists_by: str | None = None
    # Numbers by the order they were reported for, and by the policy clause whose text contains them. The flat `numbers`
    # set cannot tell that 450.000 đ is order A's total when the reply attaches it to order B.
    order_numbers: dict[str, set[str]] = field(default_factory=dict)
    clause_numbers: dict[str, set[str]] = field(default_factory=dict)


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


def _record_by_entity(evidence: Evidence, result: Any, default_order: str | None) -> None:
    """File each number of a tool result under the order it describes and under the clause it quotes."""

    def visit(node: Any, order: str | None) -> None:
        if isinstance(node, dict):
            for key in ("order_code", "code"):
                value = node.get(key)
                if isinstance(value, str) and ORDER_CODE_RE.fullmatch(value):
                    order = value.upper()
                    break
            clause = node.get("clause_id")
            if isinstance(clause, str) and isinstance(node.get("text"), str):
                evidence.clause_numbers.setdefault(clause, set()).update(
                    normalize_number(n) for n in _ANY_NUMBER_RE.findall(node["text"])
                )
            for value in node.values():
                visit(value, order)
        elif isinstance(node, list):
            for value in node:
                visit(value, order)
        elif order is not None and isinstance(node, (int, float, str)):
            evidence.order_numbers.setdefault(order, set()).update(
                normalize_number(n) for n in _ANY_NUMBER_RE.findall(str(node))
            )

    visit(result, default_order)


def _absorb(evidence: Evidence, tool: str, result: Any, args: Any = None) -> None:
    order_arg = (args or {}).get("order_code") if isinstance(args, dict) else None
    _record_by_entity(evidence, result, str(order_arg).upper() if isinstance(order_arg, str) and ORDER_CODE_RE.fullmatch(order_arg) else None)
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
        if node.get("case_type") == "return_request" or node.get("active_returns") or node.get("return_code"):
            evidence.return_exists_by = tool


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
            _absorb(evidence, str(call.get("tool")), call.get("result"), call.get("args"))
    # The recent-orders list is loaded from the database and shown to the model, so its codes and
    # amounts are legitimate evidence when the assistant lists the customer's orders.
    for order in (state.get("dynamic_context") or {}).get("recent_orders") or []:
        if order.get("code"):
            evidence.order_codes.setdefault(str(order["code"]).upper(), "recent_orders")
        for value in (order.get("total"),):
            if isinstance(value, int):
                evidence.numbers.setdefault(str(value), "recent_orders")
    # Cards the customer confirmed through the API in earlier turns (loaded from the database by load_context):
    # the return they created and the order they cancelled are facts even though no tool reported them.
    outcomes = (state.get("dynamic_context") or {}).get("conversation_outcomes") or {}
    for action in outcomes.get("confirmed_actions") or []:
        _absorb(evidence, "confirmed_action", action)
    return evidence


def escalation_exists(state: AgentState) -> bool:
    """A ticket exists for this conversation: created this turn, reported by an earlier tool result, or still open."""
    if any(tc.get("tool") == "escalate_to_human" and "ticket_code" in (tc.get("result") or {}) for tc in state.get("tool_calls", [])):
        return True
    if ((state.get("dynamic_context") or {}).get("conversation_outcomes") or {}).get("open_tickets"):
        return True
    return any(
        isinstance(m, ToolMessage) and m.name == "escalate_to_human" and '"ticket_code"' in extract_text_content(m.content)
        for m in state.get("messages", [])
    )


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


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n")


def _entity_violations(content: str, evidence: Evidence, customer_numbers: set[str]) -> list[Violation]:
    """Amounts must belong to the order the reply is talking about; numbers beside a citation must be in that clause."""
    violations: list[Violation] = []
    order: str | None = None
    elsewhere = {n for numbers in evidence.order_numbers.values() for n in numbers}
    for line in content.split("\n"):
        if not line.strip():
            order = None  # a blank line ends the paragraph, and with it the order it was about
            continue
        for sentence in _SENTENCE_BREAK.split(line):
            codes = {m.group(0).upper() for m in ORDER_CODE_RE.finditer(sentence)}
            if len(codes) == 1:
                order = next(iter(codes))
            elif len(codes) > 1:
                order = None
            cited = set(_CITATION_RE.findall(sentence))
            for value, claim in claimed_numbers(sentence).items():
                if value in customer_numbers:
                    continue
                own = evidence.order_numbers.get(order, set()) if order else set()
                if order and value not in own and value in elsewhere and value not in _policy_numbers(evidence):
                    owner = next(code for code, numbers in evidence.order_numbers.items() if value in numbers)
                    violations.append(
                        Violation("CROSS_ORDER_MISMATCH", claim, f"{claim} is a figure of order {owner}, but the reply attaches it to {order}")
                    )
                    continue
                if cited and value in _policy_numbers(evidence):
                    in_cited = any(value in evidence.clause_numbers.get(c, set()) for c in cited)
                    if not in_cited and not (order and value in own):
                        violations.append(
                            Violation(
                                "CITATION_MISMATCH",
                                claim,
                                f"{claim} is cited to {', '.join(sorted(cited))}, whose text does not contain it",
                            )
                        )
    return violations


def _policy_numbers(evidence: Evidence) -> set[str]:
    return {n for numbers in evidence.clause_numbers.values() for n in numbers}


def _proposal_exists(state: AgentState) -> bool:
    """A confirmation card was created this turn, is still waiting, or was already confirmed in this conversation
    ("bạn đã bấm Xác nhận trên thẻ" is then a true statement, not a promise of a card that does not exist)."""
    context = state.get("dynamic_context") or {}
    if state.get("pending_action") or context.get("active_pending_action"):
        return True
    if (context.get("conversation_outcomes") or {}).get("confirmed_actions"):
        return True
    return any(
        call.get("tool") in _PROPOSAL_TOOLS and "action_id" in (call.get("result") or {}) and "error_code" not in (call.get("result") or {})
        for call in state.get("tool_calls", [])
    )


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
    violations.extend(_entity_violations(content, evidence, customer_numbers))
    if _RETURN_CREATED_RE.search(lowered) and evidence.return_exists_by is None:
        violations.append(
            Violation(
                "FALSE_COMPLETION_CLAIM",
                "return request created",
                "only a proposal exists and the customer has not confirmed it: say you created a proposal and ask them to confirm "
                "on the card, not that the request was created",
            )
        )
    if _EXCHANGE_DONE_RE.search(lowered):
        violations.append(Violation("FALSE_COMPLETION_CLAIM", "exchange completed", "no tool reports a completed exchange"))
    if _PROPOSAL_CARD_RE.search(lowered) and not _proposal_exists(state):
        violations.append(
            Violation(
                "FALSE_PROPOSAL_CLAIM",
                "confirmation card",
                "no confirmation card exists: call propose_return or propose_cancel_order if the customer has given everything "
                "needed, otherwise ask for what is missing and do not mention a card or a Xác nhận button",
            )
        )
    return violations, supported
