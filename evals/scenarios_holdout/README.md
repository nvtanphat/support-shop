# Kịch bản để dành (holdout)

Tập này đo khả năng tổng quát của agent: các tình huống và cách diễn đạt **không** có trong `evals/scenarios/`.

Quy tắc:

1. Không sửa prompt, tool, guard của agent hay bộ chấm dựa trên lỗi quan sát được ở tập này. Lỗi ở đây được ghi vào báo cáo, sửa (nếu cần) bằng cách thêm kịch bản tương tự vào `evals/scenarios/` rồi sửa theo kịch bản đó.
2. Không chạy tập này trong vòng lặp phát triển hằng ngày. Chạy khi chốt một mốc: `--set holdout`.
3. Một kịch bản đã từng được dùng để sửa agent thì chuyển sang `evals/scenarios/` và viết kịch bản thay thế ở đây.
4. Kết quả mong đợi viết từ đặc tả nghiệp vụ (`docs/business-spec.md`), không từ output của agent.

## Lịch sử

- 2026-11-13: tập đầu tiên (16 kịch bản `H-*`). Sau khi chạy với Gemini, lỗi của tập này đã được phân tích để sửa agent, nên cả 16 kịch bản được chuyển sang `evals/scenarios/` (gắn tag `former_holdout`) theo quy tắc 3.
- 2026-11-13: tập thay thế, 35 kịch bản `F-*`, viết từ đặc tả trước khi sửa agent và chưa chạy với Gemini. Chỉ chạy oracle (không gọi LLM) để kiểm tra kịch bản nạp được và số tiền mong đợi khớp miền nghiệp vụ. Sinh bởi một script một lần; không sửa nội dung sau khi đã chạy với agent thật.
- 2026-11-14: lần chạy Gemini đầu tiên trên tập `F-*` (k=1): 32/35. Hai kịch bản trượt vì lỗi thật của agent (`F-RET-07`, `F-SLOT-01`) được phân tích để sửa, nên chuyển sang `evals/scenarios/` theo quy tắc 3; thay bằng `F-RET-13` và `F-SLOT-06`, viết trước khi sửa agent. `F-ORD-01` trượt do bộ chấm không nhận "đang giao" (nhãn của app cho `shipped`); không dùng để sửa nên giữ nguyên.
