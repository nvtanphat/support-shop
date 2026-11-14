"""What the assistant should do after a tool refuses, as data the model reads next to the refusal.

A domain refusal (exchange to the same variant, a return past its window, an order that can no longer be
cancelled) is information, not a dead end: the model should explain it and offer the way forward. Left alone it
tends to retry with the same arguments, search the policy over and over, or ask the customer for things that do
not change the answer. Each known code therefore carries a `next_step`, and the loop stops the tools when the same
refusal repeats (agent/turn_checks.py: stuck_refusal), and the answer must cite the policy behind a refusal
(agent/tool_requirements.py: refusal_requirements).
"""

from __future__ import annotations

from typing import Any

# error_code (propose_* / get_order) or decision_code (check_return_eligibility with eligible=false) -> next step
NEXT_STEP: dict[str, str] = {
    "EXCHANGE_SAME_VARIANT": (
        "Phân loại muốn đổi trùng với phân loại khách đang có nên không đổi được. Đừng thử lại cùng SKU. Dùng "
        "check_variant_stock để xem còn phân loại khác cùng sản phẩm không; nếu không có, nói rõ không đổi được và "
        "hỏi khách có muốn trả hàng hoàn tiền (resolution=refund) không."
    ),
    "EXCHANGE_DIFFERENT_PRODUCT": "Chỉ đổi sang phân loại khác (size, màu) của cùng sản phẩm. Giải thích với khách và đề nghị hoàn tiền nếu họ muốn.",
    "EXCHANGE_PRICE_MISMATCH": "Chỉ đổi sang phân loại cùng giá. Giải thích với khách, đề nghị phân loại cùng giá hoặc hoàn tiền.",
    "EXCHANGE_SKU_NOT_FOUND": "SKU đó không tồn tại. Lấy SKU thật bằng check_variant_stock với SKU sản phẩm khách đang có, không tự đoán.",
    "EXCHANGE_SKU_REQUIRED": "Hỏi khách muốn đổi sang size/màu nào, rồi lấy SKU thật bằng check_variant_stock.",
    "EXCHANGE_OUT_OF_STOCK": "Phân loại này hết hàng. Nói rõ cho khách, nêu phân loại khác còn hàng nếu có, hoặc đề nghị hoàn tiền.",
    "EXCHANGE_LIMIT_REACHED": "Mỗi sản phẩm chỉ đổi 1 lần. Giải thích và đề nghị hoàn tiền nếu khách muốn.",
    "EXPIRED_WINDOW": (
        "Đã quá thời hạn của lý do này. Nêu thời hạn theo điều khoản (đổi ý 7 ngày, hàng lỗi 15 ngày). Nếu khách chưa nói rõ "
        "sản phẩm có lỗi hay không, hỏi một câu để biết lý do thật; không đổi lý do thay khách."
    ),
    "CATEGORY_EXCLUDED": "Hàng thuộc nhóm loại trừ khi đổi ý (hàng xả kho, đồ lót, mỹ phẩm đã mở...). Giải thích; nếu sản phẩm bị lỗi thì lý do khác có thể áp dụng, hỏi khách.",
    "ORDER_NOT_DELIVERED": "Đơn chưa giao thành công nên chưa trả được. Nếu khách muốn dừng đơn, kiểm tra xem đơn có hủy được không.",
    "ALREADY_RETURNED": "Sản phẩm đã được trả hết số lượng. Cho khách biết và dùng get_case_status nếu họ hỏi tiến độ.",
    "ORDER_FROM_MARKETPLACE": "Đơn mua qua sàn thương mại điện tử: hướng dẫn khách tạo yêu cầu ngay trên ứng dụng của sàn.",
    "NO_ITEMS_SELECTED": "Hỏi khách muốn trả sản phẩm nào trong đơn.",
    "INVALID_QUANTITY": "Hỏi lại số lượng muốn trả.",
    "ORDER_NOT_CANCELLABLE": (
        "Đơn không hủy trực tiếp được ở trạng thái này. Tra cứu search_policy về hủy đơn và giải thích kèm mã điều khoản; nếu "
        "đơn đã giao thì hướng dẫn trả hàng, nếu đang giao thì khách có thể từ chối nhận hàng."
    ),
    "NOT_ELIGIBLE": "Không đủ điều kiện nên không tạo đề xuất. Giải thích lý do cho khách bằng điều khoản đã tra cứu.",
    "TOOL_CALL_LIMIT": "Đã gọi công cụ này đủ nhiều lần trong lượt. Trả lời khách bằng thông tin đã có hoặc hỏi thêm khách.",
}

# Refusals that retrying cannot fix: the same one twice means the turn has to end with an explanation.
BUSINESS_REFUSALS = frozenset(NEXT_STEP) - {"TOOL_CALL_LIMIT"}


def refusal_code(result: Any) -> str | None:
    """The business refusal a tool result carries, if any (error_code, or decision_code of a failed eligibility check)."""
    if not isinstance(result, dict):
        return None
    code = result.get("error_code")
    if code in NEXT_STEP:
        return str(code)
    if result.get("eligible") is False and result.get("decision_code") in NEXT_STEP:
        return str(result["decision_code"])
    return None


def with_recovery(result: Any) -> Any:
    """The same result plus `next_step` when it is a known refusal; anything else is returned untouched."""
    code = refusal_code(result)
    if code is None or "next_step" in result:
        return result
    return {**result, "next_step": NEXT_STEP[code]}
