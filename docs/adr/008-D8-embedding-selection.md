# ADR-008: Lựa chọn mô hình Embedding

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho lựa chọn mô hình embedding trong hệ thống shop-support-agent.

## Quyết định
Mô hình embedding tiếng Việt BGE-M3 chạy CPU hoặc API qua cổng EmbeddingProvider.

## Lý do và Đánh giá
Dưới 300 đoạn văn bản; chạy CPU cục bộ nhẹ và độc lập mạng.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
