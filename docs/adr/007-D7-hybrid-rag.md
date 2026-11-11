# ADR-007: RAG lai trên Postgres

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho rag lai trên postgres trong hệ thống shop-support-agent.

## Quyết định
pgvector kết hợp full-text unaccent, trộn bằng RRF.

## Lý do và Đánh giá
Tiếng Việt cần khớp cả ngữ nghĩa và từ khóa không dấu; không cần thêm database ngoài.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
