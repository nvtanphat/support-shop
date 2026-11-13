"""Deterministic tool-first requirements derived from the customer's latest message.

The system prompt asks the model to use tools, but a prompt is not a guarantee. This
module decides, from the message and the executed tool calls of the current turn,
which tool calls are mandatory before an answer may be shown. It only reads state:
it never calls tools itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

ORDER_CODE_RE = re.compile(r"\bSL-[A-Za-z0-9]+\b", re.IGNORECASE)

_HUMAN_REQUEST_RE = re.compile(
    r"gặp\s+(?:nhân\s+viên|tư\s+vấn\s+viên|người\s+thật|người)|nói\s+chuyện\s+với\s+(?:người|nhân\s+viên)"
    r"|chuyển\s+máy|tổng\s+đài\s+viên|chuyên\s+viên|trừ\s+tiền\s+(?:2|hai)\s+lần",
    re.IGNORECASE,
)

_POLICY_QUESTION_RE = re.compile(
    r"chính\s+sách|quy\s+định|điều\s+khoản|điều\s+kiện\s+(?:đổi|trả|hoàn)"
    r"|(?:bao\s+lâu|bao\s+nhiêu\s+ngày|mấy\s+ngày)"
    r"|phí\s+(?:ship|vận\s+chuyển|trả\s+hàng)"
    r"|(?:được|có\s+được)\s+(?:đổi|trả|hoàn)\b",
    re.IGNORECASE,
)

# Tools whose result gives the model real data about an order.
ORDER_DATA_TOOLS = frozenset(
    {
        "get_order",
        "lookup_order_guest",
        "track_shipment",
        "check_return_eligibility",
        "propose_return",
        "propose_cancel_order",
    }
)
POLICY_EVIDENCE_TOOLS = frozenset({"search_policy", "check_return_eligibility"})

class ToolOutcome(StrEnum):
    """What a tool call achieved. Only SUCCEEDED results may back a factual claim."""

    SUCCEEDED = "succeeded"
    # The system answered definitively that there is nothing to show (not found, access denied,
    # no policy clause). The agent may explain that, but must not claim any data.
    DEFINITIVE_NEGATIVE = "definitive_negative"
    FAILED = "failed"


_DEFINITIVE_NEGATIVE_CODES = frozenset(
    {
        "ORDER_NOT_FOUND",
        "ORDER_ACCESS_DENIED",
        "GUEST_VERIFICATION_REQUIRED",
        "CASE_NOT_FOUND",
        "TICKET_ACCESS_DENIED",
        "ITEM_NOT_FOUND",
        "RETURN_NOT_FOUND",
        "ORDER_NOT_CANCELLABLE",
    }
)


def classify_result(result: Any) -> ToolOutcome:
    """Classify a tool result. Unknown error shapes count as FAILED, never as success."""
    if not isinstance(result, dict):
        return ToolOutcome.SUCCEEDED if isinstance(result, str) and result else ToolOutcome.FAILED
    code = result.get("error_code")
    if code in _DEFINITIVE_NEGATIVE_CODES:
        return ToolOutcome.DEFINITIVE_NEGATIVE
    if code:
        return ToolOutcome.FAILED
    status = result.get("status")
    if status == "no_evidence":
        return ToolOutcome.DEFINITIVE_NEGATIVE
    if status in ("db_error", "index_unavailable", "invalid_request"):
        return ToolOutcome.FAILED
    return ToolOutcome.SUCCEEDED


@dataclass(frozen=True)
class ToolRequirement:
    """A tool call that must have happened this turn before the answer is shown."""

    key: str
    accepted_tools: frozenset[str]
    order_code: str | None
    reason: str
    preferred_tool: str


def _outcome_of(call: dict[str, Any]) -> ToolOutcome:
    return classify_result(call.get("result"))


def _is_escalated(result: Any) -> bool:
    return isinstance(result, dict) and "ticket_code" in result and classify_result(result) is ToolOutcome.SUCCEEDED


def derive_requirements(user_text: str, available_tools: Iterable[str]) -> list[ToolRequirement]:
    """Return the tool calls the latest customer message makes mandatory."""
    tools = set(available_tools)
    requirements: list[ToolRequirement] = []

    if "escalate_to_human" in tools and _HUMAN_REQUEST_RE.search(user_text):
        requirements.append(
            ToolRequirement(
                key="escalate",
                accepted_tools=frozenset({"escalate_to_human"}),
                order_code=None,
                reason="Khách yêu cầu gặp nhân viên hoặc báo sự cố thanh toán cần người xử lý.",
                preferred_tool="escalate_to_human",
            )
        )

    order_tools = ORDER_DATA_TOOLS & tools
    codes = {m.group(0).upper() for m in ORDER_CODE_RE.finditer(user_text)}
    if order_tools:
        lookup = "lookup_order_guest" if "lookup_order_guest" in tools else "get_order"
        for code in sorted(codes):
            requirements.append(
                ToolRequirement(
                    key=f"order:{code}",
                    accepted_tools=frozenset(order_tools),
                    order_code=code,
                    reason=f"Khách hỏi về đơn {code}; phải lấy dữ liệu thật của đơn.",
                    preferred_tool=lookup,
                )
            )

    if "search_policy" in tools and _POLICY_QUESTION_RE.search(user_text):
        requirements.append(
            ToolRequirement(
                key="policy",
                accepted_tools=POLICY_EVIDENCE_TOOLS & tools,
                order_code=None,
                reason="Khách hỏi về chính sách; chỉ được trả lời bằng điều khoản đã tra cứu"
                + (" (và dữ liệu của đơn đã nêu)." if codes else "."),
                preferred_tool="search_policy",
            )
        )

    return requirements


def unmet_requirements(
    requirements: Iterable[ToolRequirement], executed_calls: list[dict[str, Any]]
) -> list[ToolRequirement]:
    """Filter requirements that no executed tool call of this turn satisfies."""
    unmet: list[ToolRequirement] = []
    for req in requirements:
        satisfied = False
        for call in executed_calls:
            if call.get("tool") not in req.accepted_tools:
                continue
            outcome = _outcome_of(call)
            if outcome is ToolOutcome.FAILED:
                continue
            # DEFINITIVE_NEGATIVE ("no clause found") lets the agent say so honestly; verify_output
            # still blocks any citation or number that has no successful evidence behind it.
            if req.key == "escalate":
                satisfied = _is_escalated(call.get("result"))
            elif req.order_code is not None:
                arg = str((call.get("args") or {}).get("order_code", "")).upper()
                satisfied = arg == req.order_code
            else:
                satisfied = True
            if satisfied:
                break
        if not satisfied:
            unmet.append(req)
    return unmet


def steering_message(unmet: list[ToolRequirement]) -> str:
    """Instruction appended to the model context when it answered without a required tool."""
    lines = [
        "YÊU CẦU NGHIỆP VỤ BẮT BUỘC: câu trả lời trước chưa gọi công cụ cần thiết. "
        "Không được trả lời hoặc hứa hẹn bằng lời. Hãy gọi công cụ sau rồi mới trả lời:"
    ]
    for req in unmet:
        if req.key == "escalate":
            lines.append(
                "- escalate_to_human với reason_code phù hợp (customer_request, payment_dispute, "
                "complaints, complex_case) và summary tóm tắt khách quan."
            )
        elif req.order_code:
            lines.append(f"- {req.preferred_tool}(order_code='{req.order_code}') để lấy dữ liệu thật của đơn.")
        else:
            lines.append("- search_policy với truy vấn bám sát câu hỏi của khách để lấy điều khoản có phiên bản.")
    return "\n".join(lines)


_CLAUSE_CITATION_RE = re.compile(r"\[(POL-[A-Z0-9\-]+)\]")


def unretrieved_citations(answer: str, retrieved_clauses: Iterable[str]) -> list[str]:
    """Clause ids the draft answer cites although no lookup of this turn returned them."""
    known = set(retrieved_clauses)
    return sorted({c for c in _CLAUSE_CITATION_RE.findall(answer) if c not in known})


def citation_steering_message(clause_ids: list[str]) -> str:
    """Instruction for a draft that cites clauses nobody looked up: look them up or drop the citation."""
    return (
        "YÊU CẦU NGHIỆP VỤ BẮT BUỘC: câu trả lời trước trích dẫn điều khoản chưa được tra cứu trong lượt này: "
        + ", ".join(clause_ids)
        + ". Hãy gọi search_policy với truy vấn bám sát câu hỏi để lấy điều khoản thật rồi mới trả lời. "
        "Không trích dẫn điều khoản nào không có trong kết quả tra cứu."
    )

