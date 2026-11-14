# Tập nghiệm thu (acceptance)

16 kịch bản `A-*`, viết từ đặc tả nghiệp vụ (`docs/business-spec.md`) ngày 2026-11-14 và commit **trước** khi sửa lỗi "khách nói chật / không vừa mà agent tự chuyển sang đổi size" mà tập `evals/scenarios_final/` (`G-*`) đã phát hiện. Không lỗi nào của agent được sửa theo tập này.

Các tập trước giữ nguyên làm kết quả lịch sử: `evals/scenarios_holdout/` (`F-*`) và `evals/scenarios_final/` (`G-*`). Tập này có thêm một kịch bản truy cập đơn của người khác (tag `idor`), vì tập `G-*` không đo được cổng lộ dữ liệu khách khác.

Quy tắc:

1. Không sửa agent hay bộ chấm dựa trên lỗi quan sát được ở tập này; lỗi được ghi vào báo cáo.
2. Kết quả mong đợi viết từ đặc tả, không từ output của agent.
3. Chạy: `uv run python -m evals.harness.runner --agent langgraph --set acceptance -k 3`.

Oracle (không gọi LLM) đạt 10/16 khi chốt tập. Sáu kịch bản trượt vì oracle dựa trên danh sách từ khóa: câu có chữ "chật" bị oracle hiểu là hỏi chính sách, oracle chưa biết cụm "nói chuyện với nhân viên", và gặp "vỡ" thì oracle chọn lý do hàng lỗi thay vì hư hỏng do vận chuyển. Kịch bản không sai.
