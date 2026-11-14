# ADR-003: Framework Agent

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho framework agent trong hệ thống shop-support-agent.

## Quyết định
LangGraph 1.x với đồ thị tự định nghĩa 5 bước và checkpointer Postgres.

## Lý do và Đánh giá
Mỗi lượt là một pipeline có trace và test riêng từng node; checkpointer bền vững; hệ sinh thái phổ biến.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
