# ADR-013: Sự kiện thời gian thực qua SSE

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho sự kiện thời gian thực qua sse trong hệ thống shop-support-agent.

## Quyết định
Server-Sent Events (SSE) có chuỗi số thứ tự seq; không phát token trợ lý trước verify_output.

## Lý do và Đánh giá
Văn bản đã phát tới màn hình thì không rút lại được; chỉ phát sự kiện hoàn tất sau khi kiểm tra xong.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.
