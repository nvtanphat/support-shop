# Báo cáo kiểm chứng AI Agent

Sinh tự động bởi `python -m evals.report` từ artifact thô; không số nào được gõ tay.

## Oracle (`oracle_20261114_185713`, 67 scenario, k=1)

Scenario đạt: 67/67.

| Metric | Value | Threshold | Sample | Status |
|---|---|---|---|---|
| tool_selection_accuracy | 1.000 | 0.95 | 67/67 | PASS |
| tool_argument_accuracy | 1.000 | 0.95 | 23/23 | PASS |
| tool_execution_success | 1.000 | 0.95 | 67/67 | PASS |
| tool_order_accuracy | 1.000 | 0.95 | 16/16 | PASS |
| missing_slot_clarification | 1.000 | 0.95 | 9/9 | PASS |
| multi_turn_follow_up | 1.000 | 0.95 | 10/10 | PASS |
| task_success | 1.000 | 0.9 | 67/67 | PASS |
| business_policy_compliance | 1.000 | 0.99 | 67/67 | PASS |
| unauthorized_financial_actions | 0.000 | 0 | 0/67 | PASS |
| false_financial_completion_claims | 0.000 | 0 | 0/67 | PASS |
| cross_customer_data_leakage | 0.000 | 0 | 0/3 | PASS |

## Null (`null_20261114_190028`, 67 scenario, k=1)

Scenario đạt: 10/67.

| Metric | Value | Threshold | Sample | Status |
|---|---|---|---|---|
| tool_selection_accuracy | 0.000 | 0.95 | 0/67 | FAIL |
| tool_argument_accuracy | 0.000 | 0.95 | 0/23 | FAIL |
| tool_execution_success | 0.000 | 0.95 | 0/67 | FAIL |
| tool_order_accuracy | 0.000 | 0.95 | 0/16 | FAIL |
| missing_slot_clarification | 0.000 | 0.95 | 0/9 | FAIL |
| multi_turn_follow_up | 0.100 | 0.95 | 1/10 | FAIL |
| task_success | 0.149 | 0.9 | 10/67 | FAIL |
| business_policy_compliance | 1.000 | 0.99 | 67/67 | PASS |
| unauthorized_financial_actions | 0.000 | 0 | 0/67 | PASS |
| false_financial_completion_claims | 0.000 | 0 | 0/67 | PASS |
| cross_customer_data_leakage | 0.000 | 0 | 0/3 | PASS |

## Gemini (`langgraph_20261114_184916`, 67 scenario, k=1)

Scenario đạt: 67/67.

| Metric | Value | Threshold | Sample | Status |
|---|---|---|---|---|
| tool_selection_accuracy | 1.000 | 0.95 | 67/67 | PASS |
| tool_argument_accuracy | 1.000 | 0.95 | 23/23 | PASS |
| tool_execution_success | 1.000 | 0.95 | 67/67 | PASS |
| tool_order_accuracy | 1.000 | 0.95 | 16/16 | PASS |
| missing_slot_clarification | 1.000 | 0.95 | 9/9 | PASS |
| multi_turn_follow_up | 1.000 | 0.95 | 10/10 | PASS |
| task_success | 1.000 | 0.9 | 67/67 | PASS |
| business_policy_compliance | 1.000 | 0.99 | 67/67 | PASS |
| unauthorized_financial_actions | 0.000 | 0 | 0/67 | PASS |
| false_financial_completion_claims | 0.000 | 0 | 0/67 | PASS |
| cross_customer_data_leakage | 0.000 | 0 | 0/3 | PASS |

Độ trễ mỗi scenario: p50 9.14s, p95 22.44s, tổng 814s. Token: 2182717 vào, 20416 ra, 256 lần gọi LLM.

Nhóm lỗi: không có

## Retrieval holdout (policy_queries_holdout, ngưỡng chốt từ bộ độc lập trước khi chấm)

| Khôi phục dấu | Tập | Ngưỡng | R@1 | R@1 (đủ mọi điều khoản) | R@4 | MRR | Từ chối ngoài phạm vi | Từ chối nhầm | Mẫu (hợp lệ/ngoài phạm vi) |
|---|---|---|---|---|---|---|---|---|---|
| có | calibration | -4.76 | 0.81 | 0.75 | 0.952 | 0.869 | 0.938 | 0.048 | 42/16 |
| có | holdout | -4.76 | 0.929 | 0.893 | 0.982 | 0.964 | 1.0 | 0.0 | 28/20 |

## Ma trận nghiệm thu

| Tiêu chí | Ngưỡng | Kết quả đo | Trạng thái |
|---|---|---|---|
| P0/P1 regression tests | 100% pass | 422 pass, 0 fail, 0 skip | PASS |
| Tool Selection Accuracy | >= 0.95 | 1.000 (67/67) | PASS |
| Tool Argument Accuracy | >= 0.95 | 1.000 (23/23) | PASS |
| Successful Required Tool Execution | >= 0.95 | 1.000 (67/67) | PASS |
| Tool execution order | >= 0.95 | 1.000 (16/16) | PASS |
| Missing-Slot Clarification Accuracy | >= 0.95 | 1.000 (9/9) | PASS |
| Multi-Turn Follow-up Resolution | >= 0.95 | 1.000 (10/10) | PASS |
| Real LLM End-to-End Task Success | >= 0.9 | 1.000 (67/67) | PASS |
| Business Policy Compliance | >= 0.99 | 1.000 (67/67) | PASS |
| Unauthorized Financial Actions | <= 0 | 0.000 (0/67) | PASS |
| False Financial Completion Claims | <= 0 | 0.000 (0/67) | PASS |
| Cross-Customer Data Leakage | <= 0 | 0.000 (0/3) | PASS |
| Valid Citation Provenance | 100% | 97/97 citations backed by a successful lookup | PASS |
| Supported Factual Claims | >= 98% | 105/106 numeric claims match the scenario fixtures, business spec and decision table (independent of tool results and of config); 104/106 also match successful tool results | PASS |
| Independent final set, real Gemini (all gates) | >= 0.9 task success, every gate | task success 1.000 (48/48, k=3); not sampled: multi_turn_follow_up | PASS |
| RAG Recall@1 | >= 0.90 | 0.929 (holdout, n=28/20, ngưỡng chốt từ bộ độc lập) | PASS |
| RAG Recall@4 | >= 0.95 | 0.982 (holdout, n=28/20, ngưỡng chốt từ bộ độc lập) | PASS |
| Unsupported-Query Rejection | >= 0.95 | 1.0 (holdout, n=28/20, ngưỡng chốt từ bộ độc lập) | PASS |
| Checkpoint and State Recovery | 100% pass | 4 PostgreSQL tests pass | PASS |
| Required Backend/Frontend CI Checks | 100% pass | GitHub Actions run 43598503294 on b40cb19: lint & type check, backend + PostgreSQL, frontend + Playwright | PASS |

**AI AGENT ACCEPTANCE: PASS**

## Bằng chứng và giới hạn của kết luận

Phần này viết tay; mọi con số ở trên được sinh từ artifact trong `evals/results/`. Mã được đo: `8ab64d9` (lần sửa cuối của agent; các commit sau chỉ tách module và sửa tài liệu, hành vi không đổi).

**Nghiệm thu độc lập.** Tập `evals/scenarios_acceptance/` (16 kịch bản `A-*`, viết từ đặc tả và commit ở `f423f8a` trước lần sửa cuối), Gemini thật, k=3: **48/48, mọi cổng đạt**, 0 hành động tài chính trái phép, 0 khẳng định hoàn tất sai, 0/3 lộ dữ liệu khách khác. Tập không có kịch bản nhiều lượt nên cổng hội thoại đa lượt không có mẫu ở đây; khả năng này được đo ở tập phát triển (10/10) và tập `F-*` (18/18, k=3).

**Đường đi tới kết quả đó.** Mỗi tập độc lập, khi lỗi của nó đã được phân tích để sửa agent, không còn độc lập; nó được giữ lại làm kết quả lịch sử và việc nghiệm thu chuyển sang một tập mới viết trước lần sửa kế tiếp:

| Tập | Mã đo | Kết quả | Lỗi tìm thấy (đã sửa qua tập phát triển) |
|---|---|---|---|
| `H-*` (holdout đầu, nay trong `dev`) | trước phiên này | 38/48 (k=3) | đoán đơn khi khách có nhiều đơn; lý do mô tả bằng triệu chứng; câu trả lời đúng bị chặn vì thiếu bằng chứng của lượt trước; phiếu hỗ trợ trùng |
| `F-*` (`evals/scenarios_holdout/`) | `bade1bf` | 101/105 (k=3), trượt cổng hỏi lại 14/15 | hỏi dồn một đơn sau khi liệt kê; nhãn trạng thái lệch với thẻ đơn |
| `G-*` (`evals/scenarios_final/`) | `1b58e7f` | 59/63 (k=3), trượt cổng hỏi lại 14/15 | khách nói hàng chật và muốn trả thì agent tự chuyển sang đổi size. Lần trượt của cổng hỏi lại là do Gemini trả 503 (quá tải) ba lần liên tiếp, vẫn được tính là trượt |
| `A-*` (`evals/scenarios_acceptance/`) | `8ab64d9` | **48/48 (k=3)** | không |

**Tập phát triển** (`dev`, 67 kịch bản, k=1, mã `8ab64d9`): 67/67. Tập này gồm các kịch bản đã dùng để sửa agent, nên không chứng minh khả năng tổng quát.

**Ứng dụng thật** (`evals/e2e/live_acceptance.py`: HTTP API, PostgreSQL, Gemini, mô hình retrieval thật; mã `bade1bf`): 16/16. S12 trượt ở lần chạy liền vì dữ liệu demo được seed theo mốc 11/11 nên đơn đã quá hạn đổi ý vào ngày chạy (agent từ chối đúng); seed lại theo ngày chạy thì đạt. Playwright với API thật: 4/4.

**Lỗi tìm thấy khi thử giao diện thật và đã sửa:** nút "Gặp nhân viên" trả 500 trên PostgreSQL do deadlock (thêm test PostgreSQL: 42 request lỗi trước khi sửa, 0 sau); timeout mạng không có thông báo bị coi là lỗi vĩnh viễn; mã điều khoản hiện kèm dấu backtick; ảnh Docker không build được.

**Retrieval:** mã retrieval không đổi; tập holdout retrieval nhỏ (28 câu có đáp án, 20 câu ngoài phạm vi), khoảng tin cậy rộng. Số liệu chọn bản int8 và số ứng viên của reranker ở [ADR-008](adr/008-D8-embedding-selection.md) và [ADR-007](adr/007-D7-hybrid-rag.md).

**Giới hạn:**
- Mọi kịch bản do nhóm dự án viết; tập nghiệm thu nhỏ (16 kịch bản), nên 48/48 là bằng chứng tốt trong phạm vi các tình huống đó, không phải tỷ lệ trên khách hàng thật.
- Gemini là dịch vụ ngoài: quá tải (503) và hết hạn mức ngày đã xảy ra trong lúc đo. Agent trả câu an toàn khi đó, nhưng khách không được phục vụ trong lượt ấy.
- Chưa kiểm chứng: tải đồng thời với Gemini thật, thời gian phản hồi trên phần cứng khác, triển khai trên máy chủ thật (ảnh Docker đã build và chạy được cục bộ).
