# ADR-016: Bộ đánh giá Harness

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho bộ đánh giá harness trong hệ thống shop-support-agent.

## Quyết định
Harness tự viết trên pytest chấm trạng thái DB và pass^k.

## Lý do và Đánh giá
Chấm bằng trạng thái DB thực tế, không chấm lời văn cảm tính.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
