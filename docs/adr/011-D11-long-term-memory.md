# ADR-011: Bộ nhớ dài hạn

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho bộ nhớ dài hạn trong hệ thống shop-support-agent.

## Quyết định
Chỉ lấy dữ kiện thực tế từ bảng cơ sở dữ liệu, không cho LLM tự ghi ký ức.

## Lý do và Đánh giá
Ngăn chặn triệt để tấn công đầu độc bộ nhớ dài hạn (ASI06).

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
