# Kiến trúc

Chi tiết quyết định ở [docs/adr/](adr/). Tài liệu này chỉ mô tả cấu trúc hiện có.

## Tầng và quy tắc phụ thuộc

```
api  ->  agent  ->  domain  <-  infra
              \--->  rag
core: được mọi tầng dùng (Principal, cấu hình, đồng hồ, bảo mật)
```

- `domain/` chứa nghiệp vụ thuần (policy engine, tính tiền hoàn, state machine, service) và không phụ thuộc framework LLM.
- `infra/` cài đặt các cổng (DB, thanh toán, vận chuyển, outbox, LLM).
- `agent/` là đồ thị LangGraph; tool chỉ đọc hoặc tạo đề xuất, không ghi trạng thái đơn hay tiền.
- `api/` xác thực, phân quyền ở tầng service, SSE.

## Một lượt hội thoại

`load_context` -> `screen_input` -> `agent` (vòng gọi tool có hạn mức) -> `verify_output` -> `persist_emit`. Văn bản của trợ lý chỉ được phát sau `verify_output`.

Trong node `agent`, các guard xác định chạy ngoài LLM: `tool_requirements` (tool bắt buộc), `slot_guard` (tham số phải có nguồn trong hội thoại hoặc tool), `proposal_guard` (không đề xuất trùng), `grounding` (số liệu và tuyên bố hoàn tất phải có bằng chứng từ tool thành công). Trạng thái lượt: `completed`, `synthesized`, `requirements_unmet`, `degraded`. Xem [ADR 022](adr/022-D22-agent-turn-control.md).

## Vòng đời một hành động ghi

1. Tool `propose_*` tạo `PendingAction` kèm `preview_hash`; thời hạn lấy từ `pending_action_ttl_minutes` trong `config/policy/rules.yaml`.
2. Khách gọi `POST /actions/{id}/confirm` với `preview_hash`; service kiểm tra lại điều kiện và tính tiền.
3. Cần duyệt (hoàn từ 500.000 đ hoặc rủi ro cao) thì tạo `ApprovalRequest`; nhân viên quyết định qua `/staff/approvals/{id}/decision`.
4. Sự kiện được ghi vào `outbox_events` cùng giao dịch; worker giải ngân và `PaymentReconciler` đối soát các khoản kẹt.

## Dữ liệu và trạng thái

- Cột, khóa và ràng buộc: [data-dictionary.md](data-dictionary.md).
- Tin nhắn và sự kiện SSE có `seq` cấp phát nguyên tử; client kết nối lại bằng `Last-Event-ID`.
- Checkpoint hội thoại: `AsyncPostgresSaver` trên PostgreSQL, SQLite bền cho chạy cục bộ.
- Phân quyền theo chủ sở hữu kiểm ở tầng service và có test cho từng điểm cuối. Chưa dùng row-level security của PostgreSQL.

## Chính sách và RAG

Nguồn duy nhất là `config/policy/rules.yaml`; `rag/generator.py` sinh văn bản, `index-policies` lập chỉ mục. BM25, chuẩn hóa câu hỏi, khôi phục dấu, reranker tùy chọn, ngưỡng từ chối. Xem README.
