# ADR-005: Nạp quy trình tác nghiệp

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho nạp quy trình tác nghiệp trong hệ thống shop-support-agent.

## Quyết định
Nhúng tĩnh 6 quy trình nghiệp vụ vào system prompt.

## Lý do và Đánh giá
Khoảng 1.200 token, tận dụng tốt prompt caching của các nhà cung cấp LLM.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
