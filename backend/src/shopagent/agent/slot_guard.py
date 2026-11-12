"""Reject tool arguments the model could only have guessed.

Every slot that identifies a customer's data must come from somewhere verifiable: the
customer's own words, the recent-orders list loaded from the database, or an earlier tool
result. A guessed value is answered with a MISSING_SLOT result that tells the model to ask
the customer instead of calling the tool.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

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
# Words by which a customer states each reason (accent-stripped). The model may only pick a
# reason the customer actually expressed; anything else is asked, never inferred.
_REASON_WORDS: dict[str, tuple[str, ...]] = {
    "defective": ("loi", "rach", "hong", "bung", "soi chi", "toe", "phai mau", "kem chat luong"),
    "damaged_in_transit": ("mop", "vo", "bep", "hu hai", "van chuyen", "ship lam"),
    "wrong_item": ("giao sai", "sai hang", "sai mau", "sai size", "nham", "khong phai"),
    "missing_item": ("thieu", "mat phu kien", "khong du"),
    "not_as_described": ("khong giong", "khac mo ta", "khac hinh", "khac anh"),
    "change_of_mind": ("doi y", "khong thich", "khong vua", "khong hop", "chat", "rong", "khong ung", "khong muon"),
}
_RESOLUTIONS = frozenset(r.value for r in ReturnResolution)


class GroundingContext:
    """Values the model is allowed to reuse, collected from verifiable sources."""

    def __init__(self, messages: Iterable[BaseMessage], recent_order_codes: Iterable[str]) -> None:
        self._order_codes: set[str] = {c.upper() for c in recent_order_codes}
        self._tool_text: list[str] = []
        self._human_text: list[str] = []
        self._item_names: dict[str, tuple[str, int]] = {}
        for msg in messages:
            if isinstance(msg, HumanMessage):
                text = extract_text_content(msg.content)
                self._human_text.append(remove_vietnamese_accents(text))
                self._order_codes.update(m.group(0).upper() for m in ORDER_CODE_RE.finditer(text))
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

    def customer_said(self, words: Iterable[str]) -> bool:
        return any(_has_word(text, w) for text in self._human_text for w in words)

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
    if reason not in _REASONS or not grounding.customer_said(_REASON_WORDS[reason]):
        return _missing(
            "reason_code",
            f"Khách chưa nêu lý do đổi trả. Hãy hỏi khách lý do rồi mới chọn mã trong {sorted(_REASONS)}.",
        )
    if args.get("resolution", "refund") not in _RESOLUTIONS:
        return _missing("resolution", "Hãy hỏi khách muốn hoàn tiền (refund) hay đổi hàng (exchange).")
    if tool == "propose_return" and args.get("resolution") == "exchange" and not args.get("exchange_sku"):
        return _missing("exchange_sku", "Khách đổi hàng: hãy hỏi mẫu/size mới rồi kiểm tra tồn kho bằng check_variant_stock.")
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


def recent_order_codes(dynamic_context: dict[str, Any]) -> list[str]:
    """Order codes from the database-backed recent-orders list in the turn context."""
    return [str(o["code"]) for o in dynamic_context.get("recent_orders") or [] if o.get("code")]


def serialize_result(result: Any) -> str:
    return result if isinstance(result, str) else json.dumps(result, default=str, ensure_ascii=False)
