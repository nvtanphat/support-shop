# Tập nghiệm thu độc lập (final)

21 kịch bản `G-*`, viết từ đặc tả nghiệp vụ (`docs/business-spec.md`) ngày 2026-11-14, sau khi tập `evals/scenarios_holdout/` (`F-*`) đã được đo bằng Gemini và hai lỗi của nó đã được phân tích. Tập này được commit **trước** khi sửa hai lỗi đó, nên không lỗi nào của agent được sửa theo nó.

Vì sao có tập này: lần đo k=3 trên `F-*` cho 101/105 nhưng trượt cổng hỏi lại khi thiếu thông tin (14/15). Rút tiếp các kịch bản đang trượt khỏi `F-*` để thay thế sẽ làm số liệu kém tin cậy, nên `F-*` được giữ nguyên làm kết quả lịch sử, và việc nghiệm thu sau khi sửa dùng tập mới này.

Quy tắc giống tập holdout:

1. Không sửa agent hay bộ chấm dựa trên lỗi quan sát được ở tập này; lỗi được ghi vào báo cáo.
2. Kết quả mong đợi viết từ đặc tả, không từ output của agent.
3. Chạy: `uv run python -m evals.harness.runner --agent langgraph --set final -k 3`.

Oracle (không gọi LLM) đạt 18/21 khi chốt tập; ba kịch bản trượt vì oracle dựa trên danh sách từ khóa ("bị trừ tiền hai lần", "chật", câu có chữ "size"), không phải vì kịch bản sai.
