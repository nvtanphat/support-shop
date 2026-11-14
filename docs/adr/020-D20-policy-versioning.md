# ADR-020: Phiên bản chính sách áp dụng cho đơn

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho phiên bản chính sách áp dụng cho đơn trong hệ thống shop-support-agent.

## Quyết định
Đơn hàng mang policy_version có hiệu lực tại thời điểm đặt hàng (placed_at).

## Lý do và Đánh giá
Bảo vệ quyền lợi khách hàng; tránh việc cập nhật chính sách làm thay đổi quyền của đơn cũ.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
