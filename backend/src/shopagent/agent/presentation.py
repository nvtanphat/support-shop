"""Remove internal codes from a verified reply before the customer sees it.

The prompt asks the model to speak plain Vietnamese, but it still writes things like
"Đã giao (`delivered`)" or "giảm giá cuối mùa / final_sale". Codes that only mean something inside the
system are dropped when they follow their own label, and translated when they stand alone.
"""

from __future__ import annotations

import re

CODE_LABELS: dict[str, str] = {
    # order status
    "pending_payment": "chờ thanh toán",
    "confirmed": "đã xác nhận",
    "packing": "đang đóng gói",
    "shipped": "đang giao",
    "out_for_delivery": "đang giao đến bạn",
    "delivery_failed": "giao không thành công",
    "delivered": "đã giao",
    "completed": "hoàn tất",
    "cancelled": "đã hủy",
    "returning_to_seller": "đang hoàn về shop",
    "returned_to_seller": "đã hoàn về shop",
    # return reasons and resolutions
    "defective": "sản phẩm bị lỗi",
    "damaged_in_transit": "hư hại khi vận chuyển",
    "wrong_item": "giao sai món",
    "missing_item": "thiếu món",
    "not_as_described": "không đúng mô tả",
    "change_of_mind": "đổi ý",
    "refund": "hoàn tiền",
    "exchange": "đổi hàng",
    # product return flags
    "final_sale": "hàng giảm giá cuối mùa",
    "sealed_cosmetic": "mỹ phẩm còn niêm phong",
    "hygiene": "hàng vệ sinh cá nhân",
    "personalized": "hàng cá nhân hóa",
}

_CODES = "|".join(sorted(map(re.escape, CODE_LABELS), key=len, reverse=True))
# "(`delivered`)" or "(delivered)" right after the label it repeats
_PARENTHESISED = re.compile(rf"\s*\(\s*`?\*?({_CODES})\*?`?\s*\)")
# "giảm giá cuối mùa / final_sale"
_SLASHED = re.compile(rf"\s*/\s*`?({_CODES})`?(?![\w-])")
# a code on its own in backticks
_BACKTICKED = re.compile(rf"`({_CODES})`")
# a clause citation in backticks: the UI turns [POL-...] into a link, and the backticks would show around it
_BACKTICKED_CITATION = re.compile(r"`\s*(\[POL-[A-Z0-9-]+\])\s*`")


def strip_internal_codes(text: str) -> str:
    text = _BACKTICKED_CITATION.sub(r"\1", text)
    text = _PARENTHESISED.sub("", text)
    text = _SLASHED.sub("", text)
    return _BACKTICKED.sub(lambda m: CODE_LABELS[m.group(1)], text)
