# ADR-018: Tách cổng tích hợp ngoài có 3 chế độ

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho tách cổng tích hợp ngoài có 3 chế độ trong hệ thống shop-support-agent.

## Quyết định
Mọi tích hợp ngoài (thanh toán, vận chuyển, email, SMS) đều qua Port + Adapter có nhãn Simulated/Sandbox/Real.

## Lý do và Đánh giá
Tách biệt môi trường thử nghiệm với môi trường thật; tiêm lỗi dễ dàng trong test.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
