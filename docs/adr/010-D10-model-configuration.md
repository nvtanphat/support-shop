# ADR-010: Cấu hình Model theo vai

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho cấu hình model theo vai trong hệ thống shop-support-agent.

## Quyết định
Khai báo vai model trong config/models.yaml, trừu tượng hóa qua factory.

## Lý do và Đánh giá
Không khóa cứng mã nguồn vào một nhà cung cấp; dễ dàng đổi model hoặc bake-off.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
