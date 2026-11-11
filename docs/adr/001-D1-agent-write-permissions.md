# ADR-001: Quyền ghi của Agent

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho quyền ghi của agent trong hệ thống shop-support-agent.

## Quyết định
Agent chỉ đề xuất hành động (propose_*), khách xác nhận qua API, không có tool ghi hay tool xác nhận.

## Lý do và Đánh giá
Loại bỏ nguy cơ excessive agency (OWASP ASI02) ở tầng kiến trúc. Model bị tấn công prompt injection cũng chỉ tạo được đề xuất vô hại.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
