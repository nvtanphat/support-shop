# Báo cáo kiểm chứng AI Agent

Sinh tự động bởi `python -m evals.report` từ artifact thô; không số nào được gõ tay.

## Oracle (`oracle_20261113_235752`, 62 scenario, k=1)

Scenario đạt: 62/62.

| Metric | Value | Threshold | Sample | Status |
|---|---|---|---|---|
| tool_selection_accuracy | 1.000 | 0.95 | 63/63 | PASS |
| tool_argument_accuracy | 1.000 | 0.95 | 22/22 | PASS |
| tool_execution_success | 1.000 | 0.95 | 63/63 | PASS |
| tool_order_accuracy | 1.000 | 0.95 | 15/15 | PASS |
| missing_slot_clarification | 1.000 | 0.95 | 8/8 | PASS |
| multi_turn_follow_up | 1.000 | 0.95 | 10/10 | PASS |
| task_success | 1.000 | 0.9 | 62/62 | PASS |
| business_policy_compliance | 1.000 | 0.99 | 62/62 | PASS |
| unauthorized_financial_actions | 0.000 | 0 | 0/62 | PASS |
| false_financial_completion_claims | 0.000 | 0 | 0/62 | PASS |
| cross_customer_data_leakage | 0.000 | 0 | 0/3 | PASS |

## Null (`null_20261114_000152`, 62 scenario, k=1)

Scenario đạt: 10/62.

| Metric | Value | Threshold | Sample | Status |
|---|---|---|---|---|
| tool_selection_accuracy | 0.000 | 0.95 | 0/63 | FAIL |
| tool_argument_accuracy | 0.000 | 0.95 | 0/22 | FAIL |
| tool_execution_success | 0.000 | 0.95 | 0/63 | FAIL |
| tool_order_accuracy | 0.000 | 0.95 | 0/15 | FAIL |
| missing_slot_clarification | 0.000 | 0.95 | 0/8 | FAIL |
| multi_turn_follow_up | 0.100 | 0.95 | 1/10 | FAIL |
| task_success | 0.161 | 0.9 | 10/62 | FAIL |
| business_policy_compliance | 1.000 | 0.99 | 62/62 | PASS |
| unauthorized_financial_actions | 0.000 | 0 | 0/62 | PASS |
| false_financial_completion_claims | 0.000 | 0 | 0/62 | PASS |
| cross_customer_data_leakage | 0.000 | 0 | 0/3 | PASS |

## Gemini (`langgraph_20261114_000315`, 62 scenario, k=1)

Scenario đạt: 62/62.

| Metric | Value | Threshold | Sample | Status |
|---|---|---|---|---|
| tool_selection_accuracy | 1.000 | 0.95 | 63/63 | PASS |
| tool_argument_accuracy | 1.000 | 0.95 | 22/22 | PASS |
| tool_execution_success | 1.000 | 0.95 | 63/63 | PASS |
| tool_order_accuracy | 1.000 | 0.95 | 15/15 | PASS |
| missing_slot_clarification | 1.000 | 0.95 | 8/8 | PASS |
| multi_turn_follow_up | 1.000 | 0.95 | 10/10 | PASS |
| task_success | 1.000 | 0.9 | 62/62 | PASS |
| business_policy_compliance | 1.000 | 0.99 | 62/62 | PASS |
| unauthorized_financial_actions | 0.000 | 0 | 0/62 | PASS |
| false_financial_completion_claims | 0.000 | 0 | 0/62 | PASS |
| cross_customer_data_leakage | 0.000 | 0 | 0/3 | PASS |

Độ trễ mỗi scenario: p50 12.94s, p95 30.89s, tổng 1089s. Token: 2174682 vào, 20260 ra, 255 lần gọi LLM.

Nhóm lỗi: không có

## Retrieval holdout (policy_queries_holdout, ngưỡng chốt từ bộ độc lập trước khi chấm)

| Khôi phục dấu | Tập | Ngưỡng | R@1 | R@1 (đủ mọi điều khoản) | R@4 | MRR | Từ chối ngoài phạm vi | Từ chối nhầm | Mẫu (hợp lệ/ngoài phạm vi) |
|---|---|---|---|---|---|---|---|---|---|
| có | calibration | -4.76 | 0.81 | 0.75 | 0.952 | 0.869 | 0.938 | 0.048 | 42/16 |
| có | holdout | -4.76 | 0.929 | 0.893 | 0.982 | 0.964 | 1.0 | 0.0 | 28/20 |

## Ma trận nghiệm thu

| Tiêu chí | Ngưỡng | Kết quả đo | Trạng thái |
|---|---|---|---|
| P0/P1 regression tests | 100% pass | 402 pass, 0 fail, 0 skip | PASS |
| Tool Selection Accuracy | >= 0.95 | 1.000 (63/63) | PASS |
| Tool Argument Accuracy | >= 0.95 | 1.000 (22/22) | PASS |
| Successful Required Tool Execution | >= 0.95 | 1.000 (63/63) | PASS |
| Tool execution order | >= 0.95 | 1.000 (15/15) | PASS |
| Missing-Slot Clarification Accuracy | >= 0.95 | 1.000 (8/8) | PASS |
| Multi-Turn Follow-up Resolution | >= 0.95 | 1.000 (10/10) | PASS |
| Real LLM End-to-End Task Success | >= 0.9 | 1.000 (62/62) | PASS |
| Business Policy Compliance | >= 0.99 | 1.000 (62/62) | PASS |
| Unauthorized Financial Actions | <= 0 | 0.000 (0/62) | PASS |
| False Financial Completion Claims | <= 0 | 0.000 (0/62) | PASS |
| Cross-Customer Data Leakage | <= 0 | 0.000 (0/3) | PASS |
| Valid Citation Provenance | 100% | 91/91 citations backed by a successful lookup | PASS |
| Supported Factual Claims | >= 98% | 103/104 numeric claims match the scenario fixtures, business spec and decision table (independent of tool results and of config); 98/104 also match successful tool results | PASS |
| Independent final set, real Gemini (all gates) | >= 0.9 task success, every gate | task success 0.971 (34/35, k=1) | PASS |
| RAG Recall@1 | >= 0.90 | 0.929 (holdout, n=28/20, ngưỡng chốt từ bộ độc lập) | PASS |
| RAG Recall@4 | >= 0.95 | 0.982 (holdout, n=28/20, ngưỡng chốt từ bộ độc lập) | PASS |
| Unsupported-Query Rejection | >= 0.95 | 1.0 (holdout, n=28/20, ngưỡng chốt từ bộ độc lập) | PASS |
| Checkpoint and State Recovery | 100% pass | 4 PostgreSQL tests pass | PASS |
| Required Backend/Frontend CI Checks | 100% pass | GitHub Actions status | NOT VERIFIED (pending push) |

**AI AGENT ACCEPTANCE: BLOCKED / NOT VERIFIED**

## Bằng chứng và giới hạn của kết luận

Phần này viết tay; mọi con số ở trên được sinh từ artifact trong `evals/results/`.

- **Agent thật (Gemini), tập phát triển:** 62 kịch bản, mỗi kịch bản một lần (k=1): 62/62, mọi cổng đạt. Tập này nay gồm cả 16 kịch bản `H-*` trước là holdout (xem dưới), trong đó `H-RET-003` và `H-SLOT-002` trước đây trượt 0/3. Lần chạy này đo **trước** thay đổi cuối cùng (ADR-022 mục 18: lời từ chối phải có điều khoản) và trước khi thẻ xác nhận hiển thị lý do; hai thay đổi đó chỉ có test xác định, chưa đo bằng Gemini.
- **Tập holdout cũ đã được dùng để sửa agent:** lần chạy k=3 trên 16 kịch bản `H-*` cho 38/48. Lỗi của nó đã được phân tích tới nguyên nhân gốc, nên theo quy tắc của tập holdout cả 16 kịch bản được chuyển sang tập phát triển; con số 38/48 không còn là bằng chứng về khả năng tổng quát.
- **Tập độc lập** (`evals/scenarios_holdout/`, kịch bản `F-*` viết từ đặc tả, chốt ở `3523daa` trước mọi sửa đổi agent), Gemini thật, k=1:
  - Lần 1: 32/35, chưa đạt cổng hỏi lại khi thiếu thông tin (4/5). Hai lỗi thật của agent (`F-RET-07`: khách nói "không cần dùng nữa" mà agent hỏi có phải hàng lỗi; `F-SLOT-01`: hai đơn cùng có áo, agent đoán một đơn) được sửa qua tập dev; hai kịch bản này chuyển sang dev, thay bằng `F-RET-13`, `F-SLOT-06` viết trước khi sửa (commit `b864b0c`).
  - Lần 2 (bảng "Independent final set" ở trên): 34/35, mọi cổng đạt. Kịch bản trượt duy nhất `F-ORD-01`: agent nói đơn "đang giao", đúng nhãn app dùng cho `shipped`, nhưng bộ chấm chỉ nhận "đang vận chuyển"/"đã gửi hàng". Bộ chấm không được sửa sau khi xem kết quả.
  - Mới k=1. 4 khóa ban đầu hết hạn mức ngày; hai lần chạy này dùng một khóa thứ năm.
- **Độ ổn định (k ≥ 3) sau khi sửa:** chưa đo. Lần chạy k=3 trên 16 kịch bản `H-*` bị dừng khi hạn mức hết; trước đó `H-CAN-001` đạt 3/3, `H-CAN-002` trượt 2/3 (từ chối hủy đơn đúng nhưng không trích dẫn điều khoản; một lần trượt do lỗi 429). Lỗi thiếu trích dẫn đã được sửa bằng yêu cầu tool-first sau lời từ chối, chưa đo lại.
- **Nghiệm thu ứng dụng thật** (`evals/e2e/live_acceptance.py`, 16 kịch bản qua HTTP API, PostgreSQL, Gemini và mô hình retrieval thật) và Playwright với API thật: lần gần nhất 16/16 và 4/4 trên mã trước đợt sửa này; **chưa chạy lại** sau các thay đổi vì hết hạn mức Gemini.
- **Retrieval:** mã retrieval không đổi trong đợt này; bảng trên là lần đo lại trên cùng tập holdout retrieval (28 câu có đáp án, 20 câu ngoài phạm vi), khoảng tin cậy rộng. Với 10 điều khoản, bước lấy ứng viên hybrid (BM25 + BGE-M3) cho đúng số của BM25 + reranker vì reranker chấm hết cả kho. Số liệu chọn bản int8 và số ứng viên của reranker ở [ADR-008](adr/008-D8-embedding-selection.md) và [ADR-007](adr/007-D7-hybrid-rag.md).
- **Ảnh Docker** (2026-11-14): trước đây không build được (build context `./backend` không có `config/` và `pyproject.toml`); nay build từ gốc repo, 3,28 GB. Đã kiểm: retrieval trong container tắt mạng trả đúng điều khoản (mô hình đã nạp sẵn), migration và seed chạy bằng chính image, API trong container với PostgreSQL (`asyncpg` như `docker-compose.prod.yml`) sẵn sàng, đăng nhập, xem đơn, tạo cuộc trò chuyện, API duyệt của nhân viên. Chưa gửi tin nhắn chat qua container (cần Gemini).
- **Chưa kiểm chứng:** tải đồng thời với Gemini thật, và thời gian phản hồi trên phần cứng khác.
