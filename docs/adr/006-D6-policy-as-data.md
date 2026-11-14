# ADR-006: Chính sách dạng dữ liệu (Policy-as-Data)

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho chính sách dạng dữ liệu (policy-as-data) trong hệ thống shop-support-agent.

## Quyết định
rules.yaml là nguồn sự thật duy nhất cho luật nghiệp vụ và tài liệu chính sách sinh ra.

## Lý do và Đánh giá
Triệt tiêu hoàn toàn độ lệch giữa lời nói của bot và hành vi thực thi của code.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
