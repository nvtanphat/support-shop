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
# Tools that start a write proposal: the order must be one the customer chose, not merely one in the recent list.
_PROPOSAL_ORDER_TOOLS = frozenset({"check_return_eligibility", "propose_return", "propose_cancel_order"})
# How a customer points into the recent-orders list shown to the model (newest first). A position chooses that order;
# a vague reference ("đơn hôm qua") leaves the matching to the model among the recent orders.
_ORDER_POSITION_RE: tuple[tuple[int, re.Pattern[str]], ...] = (
    (0, re.compile(r"\bđơn(?:\s+hàng)?\s+(?:gần\s+nhất|mới\s+nhất|mới\s+đặt|vừa\s+(?:đặt|mua)|đầu\s+tiên|thứ\s+(?:nhất|1)|số\s+1)")),
    (1, re.compile(r"\bđơn(?:\s+hàng)?\s+(?:thứ\s+(?:hai|2)|số\s+2)")),
    (2, re.compile(r"\bđơn(?:\s+hàng)?\s+(?:thứ\s+(?:ba|3)|số\s+3)")),
)
_VAGUE_ORDER_REFERENCE_RE = re.compile(r"\bđơn(?:\s+hàng)?\s+(?:gần\s+đây|cuối(?:\s+cùng)?|hôm\s+(?:qua|nay|trước))")
# Words of a return request itself, not of the problem: a quote made only of these describes nothing.
_NON_DESCRIPTIVE_TOKENS = frozenset(
    {
        "tra", "doi", "hoan", "tien", "hang", "muon", "minh", "toi", "em", "ban", "shop", "don", "cho", "voi", "giup",
        "nhe", "oi", "la", "cai", "chiec", "mon", "san", "pham", "nay", "do", "vi", "bi", "da", "roi", "mua", "nhan",
        "duoc", "khong", "lai", "yeu", "cau", "ve", "hom", "thi", "ma", "va", "nhung", "cua", "co", "the",
        "quy", "khach", "sp",
    }
)
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
CLOSED_QUESTION_RE = re.compile(r"(?:phải|đúng|có đúng|đúng là)\s+(?:không|chứ|vậy)|không(?:\s+ạ)?\s*\?|phải\s+vậy|đúng\s+chứ")
_AFFIRMATION_RE = re.compile(
    r"^\s*(?:dạ|vâng|ừ|ừm|à|ờ|ok|okay|đúng|phải|chính xác|chuẩn|có|yes|y)\b[^?\n]{0,40}$", re.IGNORECASE
)
_RESOLUTIONS = frozenset(r.value for r in ReturnResolution)
# Words by which a customer asks for another variant. "Chật" or "không vừa" alone is a reason (change of mind), not a
# wish to exchange: seen live, "đi thử thấy chật, trả lại được không" was turned into a size exchange. "Đổi ý" and
# "đổi trả" contain "đổi" but ask for nothing to be exchanged, so only these phrases count.
_EXCHANGE_WORDS_VI: tuple[str, ...] = (
    "đổi size", "đổi sang", "đổi qua", "đổi cỡ", "đổi màu", "đổi phân loại", "đổi hàng", "đổi cái khác", "đổi lấy",
    "đổi lại size", "size khác", "cỡ khác", "màu khác",
)
_EXCHANGE_WORDS: tuple[str, ...] = tuple(dict.fromkeys(remove_vietnamese_accents(w) for w in _EXCHANGE_WORDS_VI))


class GroundingContext:
    """Values the model is allowed to reuse, collected from verifiable sources."""

    def __init__(self, messages: Iterable[BaseMessage], recent_order_codes: Iterable[str]) -> None:
        self._recent_list: list[str] = [c.upper() for c in recent_order_codes]
        self._recent_codes: set[str] = set(self._recent_list)
        self._order_codes: set[str] = set(self._recent_codes)
        self._customer_codes: set[str] = set()
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
                self._customer_codes.update(m.group(0).upper() for m in ORDER_CODE_RE.finditer(text))
                self._order_codes.update(self._customer_codes)
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
        if not asked or not _AFFIRMATION_RE.match(self._latest_human) or not CLOSED_QUESTION_RE.search(asked.lower()):
            return False
        return _mentions_reason(unicodedata.normalize("NFC", asked.lower()), remove_vietnamese_accents(asked), reason)

    def customer_wants_exchange(self) -> bool:
        """The customer asked for another variant, or said yes when the assistant offered one."""
        for raw, stripped in zip(self._human_raw, self._human_text, strict=True):
            words, text = (_EXCHANGE_WORDS_VI, raw) if raw != stripped else (_EXCHANGE_WORDS, stripped)
            if any(_has_word(text, w) for w in words):
                return True
        asked = unicodedata.normalize("NFC", self._assistant_before_latest.lower())
        offered = any(_has_word(asked, w) for w in _EXCHANGE_WORDS_VI)
        return offered and CLOSED_QUESTION_RE.search(asked) is not None and _AFFIRMATION_RE.match(self._latest_human) is not None

    def recent_order_list(self) -> list[str]:
        """The recent orders shown to the model, newest first: the candidates when the customer has not chosen."""
        return list(self._recent_list)

    def order_chosen_by_customer(self, code: str) -> bool:
        """The customer chose this order: typed its code, pointed into the recent list, said yes to a question naming
        it, or has only this one recent order. Being in the recent list alone is not a choice when there are several."""
        code = code.strip().upper()
        if code in self._customer_codes:
            return True
        if code in self._recent_codes:
            if len(self._recent_codes) == 1:
                return True
            positions = {i for h in self._human_raw for i, pattern in _ORDER_POSITION_RE if pattern.search(h)}
            if any(i < len(self._recent_list) and self._recent_list[i] == code for i in positions):
                return True
            if not positions and any(_VAGUE_ORDER_REFERENCE_RE.search(h) for h in self._human_raw):
                return True
        asked = {m.group(0).upper() for m in ORDER_CODE_RE.finditer(self._assistant_before_latest)}
        return asked == {code} and _AFFIRMATION_RE.match(self._latest_human) is not None

    def quote_supports_reason(self, reason: str, quote: Any) -> bool:
        """The customer's own description of the problem, copied verbatim, grounds the reason the model read from it.

        The word list cannot know every symptom ("bị rè một bên tai", "sạc không vào điện"), and a yes/no question
        after a clear description only adds a turn. The quote must be text the customer wrote, must describe something
        beyond the request and the product's name, and must not use the words of a different reason. The reason is
        shown again on the confirmation card, and shop-fault returns are checked by staff against photos.
        """
        if not isinstance(quote, str) or not quote.strip():
            return False
        needle = _squash(quote)
        if not needle or not any(needle in _squash(h) for h in self._human_raw):
            return False
        raw, stripped = unicodedata.normalize("NFC", quote.lower()), remove_vietnamese_accents(quote)
        if any(other != reason and _mentions_reason(raw, stripped, other) for other in _REASON_WORDS_VI):
            return False
        product_tokens = {tok for name, _ in self._item_names.values() for tok in tokenize_unaccent(name)}
        described = [
            tok for tok in tokenize_unaccent(ORDER_CODE_RE.sub(" ", quote))
            if tok not in _NON_DESCRIPTIVE_TOKENS and tok not in product_tokens and not tok.isdigit()
        ]
        return bool(described)

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


def _squash(text: str) -> str:
    """Lower-case, NFC, single spaces, no surrounding punctuation: how a quote is compared with the customer's text."""
    collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text.lower())).strip()
    return collapsed.strip(" .,!?;:\"'“”‘’()[]-")


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

    if tool in _PROPOSAL_ORDER_TOOLS and not grounding.order_chosen_by_customer(str(code)):
        return {
            **_missing(
                "order_code",
                "Khách có nhiều đơn gần đây và chưa nói rõ muốn xử lý đơn nào. Hãy liệt kê các đơn trong `candidates` (mã đơn, "
                "sản phẩm) và hỏi khách muốn xử lý đơn nào; không đoán một đơn rồi hỏi 'phải không'.",
            ),
            "candidates": grounding.recent_order_list(),
        }

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
    # A proposal for the very order, items and reason an eligibility check already ran for: that check passed this
    # guard, so the reason need not be quoted a second time.
    already_checked = tool == "propose_return" and grounding.eligibility_for(str(code), ids, str(reason)) is not None
    if reason not in _REASONS or not (
        already_checked
        or grounding.customer_stated_reason(str(reason))
        or grounding.quote_supports_reason(str(reason), args.get("reason_quote"))
    ):
        return _missing(
            "reason_code",
            "Chưa có căn cứ cho lý do đổi trả này. Nếu khách đã nói lý do bằng lời riêng, gọi lại công cụ với `reason_quote` "
            "là đúng đoạn khách đã viết (chép nguyên văn, không diễn đạt lại) và lý do khớp với đoạn đó: sản phẩm hỏng "
            "('bị rè một bên tai' là lỗi), hay đổi ý ('mua về thấy không cần dùng nữa', 'được tặng rồi nên dư' là đổi ý). "
            "Nếu khách chưa nói lý do, hãy hỏi lý do; nếu lời khách chưa rõ thuộc lý do nào, hỏi MỘT câu đóng nêu đúng lý do "
            "gần với lời khách, ví dụ 'Sản phẩm bị lỗi phải không ạ?' hoặc 'Bạn đổi ý không dùng nữa phải không ạ?'. "
            f"Không tự chọn lý do khi khách chưa nói gì. Mã hợp lệ: {sorted(_REASONS)}.",
        )
    if args.get("resolution", "refund") not in _RESOLUTIONS:
        return _missing("resolution", "Hãy hỏi khách muốn hoàn tiền (refund) hay đổi hàng (exchange).")
    if args.get("resolution") == "exchange" and not grounding.customer_wants_exchange():
        return _missing(
            "resolution",
            "Khách chưa yêu cầu đổi sang phân loại khác. Hàng chật, rộng hay không vừa là lý do trả hàng (đổi ý), không phải "
            "yêu cầu đổi size: khách nói muốn trả thì dùng resolution=refund. Chỉ khi khách chưa nói muốn trả hay đổi, hỏi một "
            "câu: bạn muốn trả hàng hoàn tiền hay đổi sang size khác.",
        )
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


def names_a_reason(lowered: str) -> bool:
    stripped = remove_vietnamese_accents(lowered)
    return any(_has_word(lowered, w) for words in _REASON_WORDS_VI.values() for w in words) or any(
        _has_word(stripped, w) for words in _REASON_WORDS.values() for w in words
    )


def recent_order_codes(dynamic_context: dict[str, Any]) -> list[str]:
    """Order codes from the database-backed recent-orders list in the turn context."""
    return [str(o["code"]) for o in dynamic_context.get("recent_orders") or [] if o.get("code")]


def serialize_result(result: Any) -> str:
    return result if isinstance(result, str) else json.dumps(result, default=str, ensure_ascii=False)
