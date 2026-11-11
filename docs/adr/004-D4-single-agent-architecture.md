# ADR-004: Kiến trúc một Agent duy nhất

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho kiến trúc một agent duy nhất trong hệ thống shop-support-agent.

## Quyết định
Chỉ dùng một Agent duy nhất thay vì Multi-Agent.

## Lý do và Đánh giá
11 công cụ và 6 quy trình là bài toán đơn giản; multi-agent chỉ làm tăng độ trễ, chi phí và điểm lỗi.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
