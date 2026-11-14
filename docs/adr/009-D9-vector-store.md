# ADR-009: Kho lưu trữ Vector

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho kho lưu trữ vector trong hệ thống shop-support-agent.

## Quyết định
pgvector với tìm kiếm khoảng cách cosine chính xác (không cần chỉ mục ANN).

## Lý do và Đánh giá
Khoảng dưới 300 đoạn, tìm kiếm chính xác cực nhanh và giữ trọn bộ dữ liệu trong một DB duy nhất.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
