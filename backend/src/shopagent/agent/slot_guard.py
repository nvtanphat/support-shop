"""Reject tool arguments the model could only have guessed.

Every slot that identifies a customer's data must come from somewhere verifiable: the
customer's own words, the recent-orders list loaded from the database, or an earlier tool
result. A guessed value is answered with a MISSING_SLOT result that tells the model to ask
the customer instead of calling the tool.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from shopagent.agent.tool_requirements import ORDER_CODE_RE
from shopagent.core.text import extract_text_content
from shopagent.domain.models.enums import ReturnReason, ReturnResolution
from shopagent.rag.chunker import remove_vietnamese_accents, tokenize_unaccent

_ORDER_TOOLS = frozenset(
    {
        "get_order",
        "lookup_order_guest",
        "track_shipment",
        "check_return_eligibility",
        "propose_return",
        "propose_cancel_order",
    }
)
_RETURN_TOOLS = frozenset({"check_return_eligibility", "propose_return"})
_REASONS = frozenset(r.value for r in ReturnReason)
# Words by which a customer states each reason. The model may only pick a reason the customer
# actually expressed; anything else is asked, never inferred. Words are written with diacritics and
# matched with them when the customer types with diacritics: stripped of accents, "hồng" (pink) reads as
# "hỏng" (broken), "bếp" (kitchen) as "bẹp" (dented), "vô" as "vỡ" and "trả lời" as "lỗi". Only a message
# typed without any diacritics is matched against the accent-stripped forms.
_REASON_WORDS_VI: dict[str, tuple[str, ...]] = {
    "defective": ("lỗi", "rách", "hỏng", "bung", "sợi chỉ", "sổ chỉ", "toè", "tòe", "phai màu", "kém chất lượng"),
    "damaged_in_transit": ("móp", "vỡ", "bẹp", "hư hại", "vận chuyển", "ship làm"),
    "wrong_item": ("giao sai", "sai hàng", "sai màu", "sai size", "nhầm", "không phải"),
    "missing_item": ("thiếu", "mất phụ kiện", "không đủ"),
    "not_as_described": ("không giống", "khác mô tả", "khác hình", "khác ảnh"),
    "change_of_mind": ("đổi ý", "không thích", "không vừa", "không hợp", "chật", "rộng", "không ưng", "không muốn"),
}
_REASON_WORDS: dict[str, tuple[str, ...]] = {
    reason: tuple(dict.fromkeys(remove_vietnamese_accents(w) for w in words)) for reason, words in _REASON_WORDS_VI.items()
}
# The customer answering a closed question the assistant just asked ("Sản phẩm bị lỗi phải không ạ?").
# Any yes/no question: "...phải không ạ?", "...đúng chứ?", "bạn có muốn mình tạo đề xuất không?".
_CLOSED_QUESTION_RE = re.compile(r"(?:phải|đúng|có đúng|đúng là)\s+(?:không|chứ|vậy)|không(?:\s+ạ)?\s*\?|phải\s+vậy|đúng\s+chứ")
_AFFIRMATION_RE = re.compile(
    r"^\s*(?:dạ|vâng|ừ|ừm|à|ờ|ok|okay|đúng|phải|chính xác|chuẩn|có|yes|y)\b[^?\n]{0,40}$", re.IGNORECASE
)
# A polite request without a question mark is still a question: "vui lòng cho em xin mã đơn".
_ASKS_RE = re.compile(
    r"(?:vui\s+lòng|xin|làm\s+ơn|bạn|quý\s+khách)\s+(?:\w+\s+){0,3}?(?:cho|cung\s+cấp|nhập|gửi|chọn|nói|biết)"
    r"|cho\s+(?:mình|em|tôi)\s+(?:biết|xin|hỏi)|(?:mình|em)\s+cần\s+(?:biết|thêm\s+thông\s+tin)"
)
_RESOLUTIONS = frozenset(r.value for r in ReturnResolution)


class GroundingContext:
    """Values the model is allowed to reuse, collected from verifiable sources."""

    def __init__(self, messages: Iterable[BaseMessage], recent_order_codes: Iterable[str]) -> None:
        self._order_codes: set[str] = {c.upper() for c in recent_order_codes}
        self._tool_text: list[str] = []
        self._human_text: list[str] = []
        self._human_raw: list[str] = []  # lower-cased, NFC, diacritics kept
        self._latest_human = ""
        self._assistant_before_latest = ""
        last_assistant = ""
        self._item_names: dict[str, tuple[str, int]] = {}
        for msg in messages:
            if isinstance(msg, HumanMessage):
                text = extract_text_content(msg.content)
                self._human_text.append(remove_vietnamese_accents(text))
                self._human_raw.append(unicodedata.normalize("NFC", text.lower()))
                self._latest_human, self._assistant_before_latest = text, last_assistant
                self._order_codes.update(m.group(0).upper() for m in ORDER_CODE_RE.finditer(text))
            elif isinstance(msg, AIMessage) and not msg.tool_calls:
                last_assistant = extract_text_content(msg.content)
            elif isinstance(msg, ToolMessage):
                text = extract_text_content(msg.content)
                self._tool_text.append(text)
                self._collect_items(text)
                self._order_codes.update(m.group(0).upper() for m in ORDER_CODE_RE.finditer(text))

    def _collect_items(self, tool_text: str) -> None:
        try:
            payload = json.loads(tool_text)
        except ValueError:
            return
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return
        for it in items:
            if isinstance(it, dict) and it.get("item_id"):
                self._item_names[str(it["item_id"])] = (str(it.get("product_name", "")), len(items))

    def eligibility_for(self, order_code: str, item_ids: list[str], reason_code: str) -> bool | None:
        """Result of the matching check_return_eligibility call, or None if that exact check never ran."""
        for text in reversed(self._tool_text):
            try:
                payload = json.loads(text)
            except ValueError:
                continue
            checked = payload.get("checked") if isinstance(payload, dict) else None
            if (
                isinstance(checked, dict)
                and str(checked.get("order_code", "")).upper() == order_code.upper()
                and set(checked.get("item_ids", [])) == set(item_ids)
                and checked.get("reason_code") == reason_code
            ):
                return bool(payload.get("eligible"))
        return None

    def customer_stated_reason(self, reason: str) -> bool:
        """The customer used a word for this reason, or confirmed it when the assistant asked.

        Words are read with diacritics whenever they were typed. A symptom the word list does not know ("tai nghe bị
        rè") is grounded the other way: the assistant asks a closed question that names the reason and the customer
        answers yes. The model alone never decides the reason.
        """
        for raw, stripped in zip(self._human_raw, self._human_text, strict=True):
            if _mentions_reason(raw, stripped, reason):
                return True
        return self._confirmed_after_closed_question(reason)

    def _confirmed_after_closed_question(self, reason: str) -> bool:
        asked = self._assistant_before_latest
        if not asked or not _AFFIRMATION_RE.match(self._latest_human) or not _CLOSED_QUESTION_RE.search(asked.lower()):
            return False
        return _mentions_reason(unicodedata.normalize("NFC", asked.lower()), remove_vietnamese_accents(asked), reason)

    def item_is_identified(self, item_id: str) -> bool:
        """A line of a multi-item order must be named by the customer; a single line is implicit."""
        name, siblings = self._item_names.get(item_id, ("", 0))
        if siblings <= 1:
            return True
        tokens = [t for t in tokenize_unaccent(name) if len(t) >= 2]
        return any(_has_word(text, t) for t in tokens for text in self._human_text)

    def knows_order(self, code: str) -> bool:
        return code.strip().upper() in self._order_codes

    def knows_item(self, item_id: str) -> bool:
        return any(item_id in text for text in self._tool_text)


def _mentions_reason(raw: str, stripped: str, reason: str) -> bool:
    """Whether a text uses a word for the reason: accented words when it has diacritics, plain ones when it has none."""
    if raw != stripped:
        return any(_has_word(raw, w) for w in _REASON_WORDS_VI[reason])
    return any(_has_word(stripped, w) for w in _REASON_WORDS[reason])


def _has_word(text: str, phrase: str) -> bool:
    """Whole-word match on accent-stripped text, so 'rong' is not found inside 'trong'."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _missing(slot: str, message: str) -> dict[str, Any]:
    return {"error_code": "MISSING_SLOT", "slot": slot, "message": message}


def _item_ids(tool: str, args: dict[str, Any]) -> list[str]:
    if tool == "check_return_eligibility":
        return [str(i) for i in args.get("item_ids") or []]
    return [str(it.get("item_id", "")) for it in args.get("items") or [] if isinstance(it, dict)]


def find_ungrounded_slot(
    tool: str, args: dict[str, Any], grounding: GroundingContext
) -> dict[str, Any] | None:
    """Return a MISSING_SLOT result when an argument is not backed by a verifiable source."""
    code = args.get("order_code")
    if tool in _ORDER_TOOLS and not (isinstance(code, str) and grounding.knows_order(code)):
        return _missing(
            "order_code",
            "Mã đơn hàng chưa được khách cung cấp hoặc chưa có trong danh sách đơn gần đây. "
            "Hãy hỏi khách mã đơn (hoặc cho khách chọn trong danh sách đơn gần đây), không tự suy đoán.",
        )

    if tool not in _RETURN_TOOLS:
        return None

    ids = _item_ids(tool, args)
    if not ids or not all(i and grounding.knows_item(i) for i in ids):
        return _missing(
            "item_ids",
            "Chưa xác định được sản phẩm cần đổi trả. Hãy gọi get_order để lấy danh sách sản phẩm "
            "rồi hỏi khách chọn sản phẩm; chỉ dùng item_id có trong kết quả get_order.",
        )
    if not all(grounding.item_is_identified(i) for i in ids):
        return _missing(
            "item_ids",
            "Đơn có nhiều sản phẩm và khách chưa nói rõ sản phẩm nào. Hãy liệt kê sản phẩm trong đơn "
            "và hỏi khách muốn trả sản phẩm nào; không tự chọn.",
        )
    reason = args.get("reason_code")
    if reason not in _REASONS or not grounding.customer_stated_reason(str(reason)):
        return _missing(
            "reason_code",
            "Khách chưa nêu hoặc chưa xác nhận lý do đổi trả. Nếu khách đã mô tả sự cố (ví dụ 'bị rè', 'không lên nguồn'), hãy "
            "hỏi lại bằng MỘT câu đóng nêu nhóm lý do bằng từ chuẩn (lỗi, hư hại khi vận chuyển, giao sai, thiếu, không "
            "đúng mô tả, đổi ý), ví dụ 'Sản phẩm bị lỗi phải không ạ?' (không hỏi bằng chính triệu chứng như 'bị rè phải "
            "không?'), rồi chờ khách trả lời; chỉ gọi lại công cụ sau khi khách xác nhận. Nếu khách chưa mô tả gì, hãy hỏi lý do. "
            f"Mã hợp lệ: {sorted(_REASONS)}.",
        )
    if args.get("resolution", "refund") not in _RESOLUTIONS:
        return _missing("resolution", "Hãy hỏi khách muốn hoàn tiền (refund) hay đổi hàng (exchange).")
    if tool == "propose_return" and args.get("resolution") == "exchange":
        sku = str(args.get("exchange_sku") or "").strip()
        if not sku or not grounding.knows_item(f'"{sku}"'):
            return _missing(
                "exchange_sku",
                "Khách đổi hàng: hỏi size/màu muốn đổi sang, gọi check_variant_stock với SKU sản phẩm đang có để lấy "
                "SKU thật của phân loại đó; chỉ dùng SKU có trong kết quả công cụ, không tự đoán.",
            )
    if tool == "propose_return":
        verdict = grounding.eligibility_for(str(code), ids, str(reason))
        if verdict is None:
            return {
                "error_code": "ELIGIBILITY_NOT_CHECKED",
                "message": "Chưa kiểm tra điều kiện đổi trả cho đúng đơn, sản phẩm và lý do này. Gọi check_return_eligibility trước.",
            }
        if verdict is False:
            return {
                "error_code": "NOT_ELIGIBLE",
                "message": "Kiểm tra điều kiện cho thấy yêu cầu này không đủ điều kiện; không tạo đề xuất, hãy giải thích lý do cho khách.",
            }
    return None


def _names_a_reason(lowered: str) -> bool:
    stripped = remove_vietnamese_accents(lowered)
    return any(_has_word(lowered, w) for words in _REASON_WORDS_VI.values() for w in words) or any(
        _has_word(stripped, w) for words in _REASON_WORDS.values() for w in words
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


def unasked_missing_slots(executed: list[dict[str, Any]], draft: str) -> list[str]:
    """Problems for slots a tool still reports missing at the end of the turn while the draft asks the customer nothing.

    Without a question the customer is left with a statement and no way to move on (seen live: both calls were
    refused for a missing reason and the reply was an explanation of the policy). Only the latest result of each
    tool counts, so a call that succeeded afterwards clears the problem.
    """
    latest = {call.get("tool"): call.get("result") or {} for call in executed}
    slots = sorted({str(r["slot"]) for r in latest.values() if r.get("error_code") == "MISSING_SLOT" and r.get("slot")})
    lowered = draft.lower()
    if "reason_code" in slots and _CLOSED_QUESTION_RE.search(lowered) and not _names_a_reason(lowered):
        return [
            "UNCLEAR_REASON_QUESTION: reason_code (the question does not name a reason in the standard words, so the "
            "customer's yes could not be tied to one: ask 'Sản phẩm bị lỗi phải không ạ?' or the matching reason, not the symptom)"
        ]
    if "?" in draft or _ASKS_RE.search(lowered):
        return []
    return [
        f"UNASKED_MISSING_SLOT: {slot} (a tool reported it missing and the reply asks the customer nothing: ask for it in one "
        "short question; for reason_code ask a closed question such as 'Sản phẩm bị lỗi phải không ạ?')"
        for slot in slots
    ]


def recent_order_codes(dynamic_context: dict[str, Any]) -> list[str]:
    """Order codes from the database-backed recent-orders list in the turn context."""
    return [str(o["code"]) for o in dynamic_context.get("recent_orders") or [] if o.get("code")]


def serialize_result(result: Any) -> str:
    return result if isinstance(result, str) else json.dumps(result, default=str, ensure_ascii=False)
