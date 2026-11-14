# ADR-002: Cơ chế phê duyệt

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho cơ chế phê duyệt trong hệ thống shop-support-agent.

## Quyết định
Phê duyệt là dữ liệu máy trạng thái trong Postgres + outbox, không dùng interrupt tạm dừng đồ thị.

## Lý do và Đánh giá
Duyệt có thể mất hàng giờ đến hàng ngày; khách có thể rời đi hoặc đổi chủ đề; dữ liệu duyệt cần truy vấn, lọc, kiểm toán.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
