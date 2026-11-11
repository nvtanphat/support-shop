# ADR-017: Triển khai một VM với Docker Compose và Caddy

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho triển khai một vm với docker compose và caddy trong hệ thống shop-support-agent.

## Quyết định
Docker Compose + Caddy TLS tự động trên Linux VM.

## Lý do và Đánh giá
Đơn giản, tái lập giống hệt môi trường phát triển, không bị ngủ đông như PaaS miễn phí.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
