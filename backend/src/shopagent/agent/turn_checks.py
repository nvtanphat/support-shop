"""Checks over a whole agent turn: what the executed tool calls and the draft reply say together.

`slot_guard` decides whether one tool call may run; these functions look at every call made so far in the turn and at
the model's draft, and tell the agent loop when to stop calling tools (a slot or a refusal that keeps coming back) and
when a draft leaves the customer without the question they need.
"""

from __future__ import annotations

import re
from typing import Any

from shopagent.agent.recovery import BUSINESS_REFUSALS, refusal_code
from shopagent.agent.slot_guard import CLOSED_QUESTION_RE, names_a_reason

# A polite request without a question mark is still a question: "vui lòng cho em xin mã đơn".
_ASKS_RE = re.compile(
    r"(?:vui\s+lòng|xin|làm\s+ơn|bạn|quý\s+khách)\s+(?:\w+\s+){0,3}?(?:cho|cung\s+cấp|nhập|gửi|chọn|nói|biết)"
    r"|cho\s+(?:mình|em|tôi)\s+(?:biết|xin|hỏi)|(?:mình|em)\s+cần\s+(?:biết|thêm\s+thông\s+tin)"
)

def stuck_slot(executed: list[dict[str, Any]]) -> str | None:
    """A slot that tools reported missing at least twice this turn and that nothing has resolved since.

    Calling the same tools again cannot supply what only the customer knows; the turn must end with a question
    (seen live: four refused calls in a row, then an unwanted hand-off to staff).
    """
    latest = {call.get("tool"): call.get("result") or {} for call in executed}
    counts: dict[str, int] = {}
    for call in executed:
        result = call.get("result") or {}
        if result.get("error_code") == "MISSING_SLOT" and result.get("slot"):
            counts[str(result["slot"])] = counts.get(str(result["slot"]), 0) + 1
    for slot, count in counts.items():
        still_missing = any(r.get("error_code") == "MISSING_SLOT" and r.get("slot") == slot for r in latest.values())
        if count >= 2 and still_missing:
            return slot
    return None


def stuck_refusal(executed: list[dict[str, Any]]) -> str | None:
    """The business refusal a tool returned at least twice this turn and nothing has overturned since.

    A refusal the domain gives twice will be given a third time: the turn must end with an explanation and an
    alternative instead of more tool calls (seen live: a rejected exchange was followed by nine policy searches and
    ten requests for photos).
    """
    counts: dict[str, int] = {}
    last_for_tool: dict[Any, str | None] = {}
    for call in executed:
        code = refusal_code(call.get("result"))
        last_for_tool[call.get("tool")] = code
        if code in BUSINESS_REFUSALS:
            counts[str(code)] = counts.get(str(code), 0) + 1
    for code, count in counts.items():
        if count >= 2 and code in last_for_tool.values():
            return code
    return None


def unasked_missing_slots(executed: list[dict[str, Any]], draft: str) -> list[str]:
    """Problems for slots a tool still reports missing at the end of the turn while the draft asks the customer nothing.

    Without a question the customer is left with a statement and no way to move on (seen live: both calls were
    refused for a missing reason and the reply was an explanation of the policy). Only the latest result of each
    tool counts, so a call that succeeded afterwards clears the problem.
    """
    latest = {call.get("tool"): call.get("result") or {} for call in executed}
    slots = sorted({str(r["slot"]) for r in latest.values() if r.get("error_code") == "MISSING_SLOT" and r.get("slot")})
    lowered = draft.lower()
    candidates = next(
        (r["candidates"] for r in latest.values() if r.get("slot") == "order_code" and len(r.get("candidates") or []) > 1), None
    )
    if candidates is not None and not re.search(r"đơn\s+(?:hàng\s+)?nào", lowered):
        named = {c for c in candidates if c.lower() in lowered}
        questions = [s for s in re.split(r"(?<=[.!?])\s+|\n", lowered) if "?" in s]
        asked = {c for c in candidates if any(c.lower() in q for q in questions)}
        # A guess at one order ("đơn SL-A phải không?") picks for the customer; the choice must stay theirs. Listing every
        # order first does not change that when the question itself names only one (both seen live).
        if len(named) < 2 or len(asked) == 1:
            return [
                f"ASK_WHICH_ORDER: order_code (several recent orders could be meant: {', '.join(candidates)}; list them and ask "
                "which one, instead of asking about one of them)"
            ]
    if "reason_code" in slots and CLOSED_QUESTION_RE.search(lowered) and not names_a_reason(lowered):
        return [
            "UNCLEAR_REASON_QUESTION: reason_code (the question does not name a reason in the standard words, so the "
            "customer's yes could not be tied to one: name the reason closest to the customer's words, e.g. 'Sản phẩm bị lỗi "
            "phải không ạ?' or 'Bạn đổi ý không dùng nữa phải không ạ?', not the symptom)"
        ]
    if "?" in draft or _ASKS_RE.search(lowered):
        return []
    return [
        f"UNASKED_MISSING_SLOT: {slot} (a tool reported it missing and the reply asks the customer nothing: ask for it in one "
        "short question; for reason_code ask the closed question that names the reason closest to the customer's words)"
        for slot in slots
    ]
