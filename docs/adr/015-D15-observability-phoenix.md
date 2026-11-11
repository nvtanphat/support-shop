# ADR-015: Hệ thống quan sát Observability

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho hệ thống quan sát observability trong hệ thống shop-support-agent.

## Quyết định
OpenTelemetry OTLP đẩy về Arize Phoenix một container duy nhất.

## Lý do và Đánh giá
Vừa đủ RAM máy phát triển 16GB; tuân thủ chuẩn OTel nên dễ chuyển đổi backend.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
