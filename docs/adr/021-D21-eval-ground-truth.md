# ADR-021: Nguồn đáp án đánh giá độc lập

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho nguồn đáp án đánh giá độc lập trong hệ thống shop-support-agent.

## Quyết định
Ground truth viết tay độc lập với rules.yaml; kịch bản cấm tham chiếu rules.yaml.

## Lý do và Đánh giá
Tránh lỗi đồng thuận vòng tròn: nếu rules.yaml sai thì bộ test độc lập sẽ phát hiện.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
