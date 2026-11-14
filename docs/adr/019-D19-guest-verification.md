# ADR-019: Xác minh khách vãng lai

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho xác minh khách vãng lai trong hệ thống shop-support-agent.

## Quyết định
Mã đơn ngẫu nhiên không tuần tự + OTP gửi tới số điện thoại đơn hàng qua form riêng.

## Lý do và Đánh giá
Ngăn chặn kẻ xấu đoán mã đơn hoặc dùng số điện thoại lộ lọt để mạo danh tra cứu shipper.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
