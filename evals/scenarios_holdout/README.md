# Kịch bản để dành (holdout)

Tập này đo khả năng tổng quát của agent: các tình huống và cách diễn đạt **không** có trong `evals/scenarios/`.

Quy tắc:

1. Không sửa prompt, tool, guard của agent hay bộ chấm dựa trên lỗi quan sát được ở tập này. Lỗi ở đây được ghi vào báo cáo, sửa (nếu cần) bằng cách thêm kịch bản tương tự vào `evals/scenarios/` rồi sửa theo kịch bản đó.
2. Không chạy tập này trong vòng lặp phát triển hằng ngày. Chạy khi chốt một mốc: `--set holdout`.
3. Một kịch bản đã từng được dùng để sửa agent thì chuyển sang `evals/scenarios/` và viết kịch bản thay thế ở đây.
4. Kết quả mong đợi viết từ đặc tả nghiệp vụ (`docs/business-spec.md`), không từ output của agent.

Tạo ngày 2026-11-13, 16 kịch bản; chưa chạy với Gemini lần nào.
