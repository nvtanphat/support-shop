# ADR-012: Tiến trình Worker và Outbox

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho tiến trình worker và outbox trong hệ thống shop-support-agent.

## Quyết định
Outbox trong Postgres kết hợp tiến trình worker riêng cùng ảnh Docker (FOR UPDATE SKIP LOCKED).

## Lý do và Đánh giá
Khởi động lại hoặc lỗi API không làm gián đoạn việc gọi thanh toán; không cần thêm Redis hay Celery.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
