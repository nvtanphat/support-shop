# ADR 018 - Điều khiển lượt hội thoại của Agent (tool-first, kết thúc xác định, slot grounding)

Trạng thái: chấp nhận. Giữ nguyên kiến trúc single-agent LangGraph 5 node (ADR 004); ADR này chỉ bổ sung cơ chế kiểm soát bên trong node `agent` và `verify_output`.

## Bối cảnh

Audit phát hiện: system prompt là hàng rào duy nhất cho việc gọi tool; vòng lặp cuối có thể kết thúc bằng tool call hoặc nội dung rỗng và vẫn được `verify_output` phát đi; tham số tool có thể do model suy đoán; retriever từng nuốt lỗi DB và lùi về dữ liệu in-memory; scenario eval có assertion không bao giờ được chạy.

## Quyết định

1. **Tool-first xác định** (`agent/tool_requirements.py`). Từ tin nhắn mới nhất của khách suy ra các tool bắt buộc: yêu cầu gặp nhân viên thì `escalate_to_human` (phải tạo được ticket), nhắc mã đơn thì một tool dữ liệu đơn khớp đúng mã, hỏi chính sách (không kèm mã đơn) thì `search_policy` hoặc `check_return_eligibility`. Model trả lời mà chưa đủ tool thì bị nhắc tối đa 2 lần; câu trả lời không tuân thủ không vào lịch sử. Hết lượt nhắc mà vẫn thiếu thì `turn_status = requirements_unmet` và khách nhận câu an toàn, không có lời hứa suông. Câu chào hay câu hỏi chung không bị ép gọi tool.
2. **Kết thúc xác định**. `turn_status` thuộc `completed | synthesized | requirements_unmet | degraded`. Hết `max_agent_iterations` khi tool result chưa được tổng hợp thì gọi một lượt tổng hợp không tool; lỗi hoặc timeout thì `degraded`. `verify_output` không bao giờ lấy AIMessage của lượt trước, từ chối tin nhắn còn `tool_calls` hoặc rỗng. Ngân sách (`max_agent_iterations`, `turn_timeout_s`, `tool_timeout_s`, `synthesis_timeout_s`, `max_input_tokens_per_turn`) nằm trong `config/models.yaml`.
3. **Slot grounding** (`agent/slot_guard.py`). `order_code` phải xuất hiện trong lời khách, danh sách đơn gần đây (nạp từ DB) hoặc kết quả tool trước đó; `item_id` phải có trong kết quả `get_order`; `reason_code`, `resolution` phải thuộc enum nghiệp vụ; đổi hàng cần `exchange_sku`. Vi phạm trả `MISSING_SLOT` kèm hướng dẫn hỏi khách, tool không chạy.
4. **RAG**. `HybridRetriever` bắt buộc có session hoặc `in_memory=True` (chế độ benchmark offline tường minh). Lỗi DB truyền lên tool thành `db_error`; chỉ mục rỗng là `index_unavailable`; không có điều khoản phù hợp là `no_evidence`. `as_of` mặc định là clock hiện tại, `as_of` sai là lỗi `INVALID_AS_OF`. Mỗi kết quả mang `version`, `effective_from`, `effective_to`.
5. **Bằng chứng số liệu**. `verify_output` chặn số kèm đơn vị (đ, k, ngày, %, giờ...) không xuất hiện trong tool result, lời khách hay context đã nạp.
6. **Trạng thái theo lượt**. `load_context` đặt lại `retrieved_clauses`, `tool_calls`, `turn_status`, `verified_output`, `error`; `persist_emit` ghi lại bản đã xác minh vào lịch sử hội thoại bằng message cùng `id` (hoặc thêm message mới khi lượt không có câu trả lời cuối).
7. **Eval**. Assertion lạ ở `required_facts`, `forbidden`, `db`, hoặc khóa `expect` làm scenario không nạp được hoặc làm lượt chấm FAIL. Thêm `required_tools`, `required_tool_args`, `tool_ordering`, `asks_for`, và kiểm tra `order` của return request.

## Bổ sung sau đợt đo Gemini thật

8. **Checkpoint PostgreSQL**: dùng `AsyncPostgresSaver` trên pool async, mở trong lifespan; `PostgresSaver` đồng bộ gây `NotImplementedError` với `graph.ainvoke` (nguyên nhân CI đỏ). Không lùi về kho khác.
9. **Phân loại kết quả tool**: `succeeded`, `definitive_negative`, `failed`; chỉ `succeeded` làm bằng chứng. Mỗi câu khẳng định được truy về tool sinh ra nó (`claim_evidence`).
10. **Chốt chặn nghiệp vụ**: không tạo đề xuất thứ hai trong một lượt hoặc khi thẻ cùng loại còn hiệu lực; `propose_return` chỉ chạy sau một `check_return_eligibility` khớp đúng đơn, sản phẩm, lý do và kết quả đủ điều kiện.
11. **Lỗi LLM**: thử lại lỗi tạm thời (503/504/429) có backoff và tôn trọng gợi ý "retry in Ns"; lỗi yêu cầu sai không thử lại; một nhóm key dùng chung toàn tiến trình, key hết quota bị bỏ qua có thời hạn.
12. **RAG**: BM25 kèm chuẩn hóa câu hỏi thay token-overlap/hashed n-gram. Reranker cross-encoder (~2 giây mỗi lần tra) được bật trong cấu hình: câu hỏi được khôi phục dấu trước khi chấm (AUC tách câu ngoài phạm vi từ 0,86 lên 0,985), và điểm tốt nhất dưới `min_score` nghĩa là không có điều khoản phù hợp. Ngưỡng chốt trên benchmark_v2, đo một lần trên benchmark_v3_holdout viết sau: từ chối 20/20, không từ chối nhầm câu hợp lệ nào.

## Hạn chế đã biết

- Bộ nhúng từ vựng băm (`FastLexicalEmbedding`) không tách được câu hỏi ngoài phạm vi khỏi câu hỏi trong phạm vi bằng ngưỡng điểm (đo trên 80 câu hỏi dương và 20 câu âm, các ngưỡng độ phủ từ và độ hiếm của token đều làm mất câu dương hoặc không loại được câu âm). Việc từ chối câu hỏi ngoài phạm vi vì vậy dựa vào model, prompt và kiểm tra số liệu, và được đo ở eval đầu-cuối chứ không ở tầng retrieval.
- Số liệu retrieval dựa trên tập nhỏ (holdout: 28 câu hợp lệ, 20 câu ngoài phạm vi) nên khoảng tin cậy rộng; câu ngoài phạm vi sát chủ đề (ví dụ trả góp) vẫn có thể lọt qua ngưỡng, khi đó prompt và `verify_output` là lớp chặn tiếp theo.
- Slot `reason_code`/`resolution` chỉ được kiểm tra thuộc enum, chưa kiểm tra được khách có thực sự nói lý do đó.
