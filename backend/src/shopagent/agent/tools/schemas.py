"""Input schemas the model sees for each domain tool."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchPolicyInput(BaseModel):
    query: str = Field(min_length=2, description="Nội dung hoặc chủ đề cần tra cứu chính sách (ví dụ: đổi trả hàng lỗi, thời gian hoàn tiền, phí trả hàng đổi ý).")
    as_of: str | None = Field(default=None, description="Thời điểm áp dụng chính sách theo định dạng ISO nếu gắn với đơn hàng cũ.")


class LookupOrderGuestInput(BaseModel):
    order_code: str = Field(min_length=3, description="Mã đơn hàng cần tra cứu (ví dụ: SL-123456).")


class ListMyOrdersInput(BaseModel):
    limit: int = Field(default=5, ge=1, le=10, description="Số lượng đơn hàng cần lấy (tối đa 10).")


class GetOrderInput(BaseModel):
    order_code: str = Field(min_length=3, description="Mã đơn hàng cần xem chi tiết (ví dụ: SL-123456).")


class TrackShipmentInput(BaseModel):
    order_code: str = Field(min_length=3, description="Mã đơn hàng cần theo dõi vận chuyển.")


class CheckReturnEligibilityInput(BaseModel):
    order_code: str = Field(min_length=3, description="Mã đơn hàng cần kiểm tra đổi trả.")
    item_ids: list[str] = Field(min_length=1, description="Danh sách item_id của các sản phẩm muốn trả (tối thiểu 1 sản phẩm).")
    reason_code: str = Field(description="Lý do đổi trả: defective, damaged_in_transit, wrong_item, missing_item, not_as_described, hoặc change_of_mind.")
    resolution: str = Field(default="refund", description="refund (hoàn tiền) hoặc exchange (đổi hàng).")


class CheckVariantStockInput(BaseModel):
    sku: str = Field(min_length=2, description="Mã SKU của phân loại sản phẩm cần kiểm tra tồn kho.")


class GetCaseStatusInput(BaseModel):
    case_code: str | None = Field(default=None, description="Mã yêu cầu trả hàng (RT-...), mã hoàn tiền (RF-...), hoặc mã phiếu hỗ trợ (TK-...).")


class ProposeCancelOrderInput(BaseModel):
    order_code: str = Field(min_length=3, description="Mã đơn hàng muốn đề xuất hủy.")
    reason: str = Field(default="customer_request", description="Lý do hủy đơn từ khách hàng.")


class ProposeReturnInput(BaseModel):
    order_code: str = Field(min_length=3, description="Mã đơn hàng muốn tạo đề xuất đổi trả.")
    items: list[dict[str, Any]] = Field(min_length=1, description="Danh sách sản phẩm cần trả kèm số lượng: [{'item_id': str, 'qty': int}].")
    reason_code: str = Field(description="Lý do đổi trả.")
    resolution: str = Field(default="refund", description="refund hoặc exchange.")
    exchange_sku: str | None = Field(default=None, description="Mã SKU mới muốn đổi sang nếu resolution=exchange.")
    refund_method: str = Field(default="original", description="Phương thức hoàn tiền: original hoặc bank_transfer.")


class EscalateToHumanInput(BaseModel):
    reason_code: str = Field(description="Lý do cần chuyển nhân viên: complex_case, customer_request, payment_dispute, complaints.")
    summary: str = Field(min_length=5, description="Tóm tắt ngắn gọn vấn đề của khách hàng để nhân viên nắm bắt.")
