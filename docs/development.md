# Phát triển

## Cấu hình đáng chú ý

- `RETRIEVAL_RERANKER_ENABLED=false` tắt reranker (mặc định bật trong `config/app.yaml`; mô hình khoảng 1 GB RAM)
- `RETRIEVAL_EMBEDDING_ENABLED=false` tắt nửa embedding của bước lấy ứng viên (mặc định bật; BGE-M3 cần khoảng 2,3 GB ổ đĩa và 2-3 GB RAM, lần đầu tải mất vài phút). Tắt thì retrieval chỉ còn BM25 + reranker. Đổi model trong `retrieval.embedding.model` rồi chạy `index-policies` để embed lại.
- `GEMINI_API_KEY` nhận nhiều khóa cách nhau bằng dấu phẩy; khóa bị giới hạn tốc độ được nghỉ tạm và hệ thống chuyển sang khóa khác.
- Hạn mức vòng lặp agent, thời gian chờ và số lần thử lại LLM ở [config/models.yaml](../config/models.yaml).
- Bộ nhớ đệm nặng (mô hình reranker) đặt qua `FASTEMBED_CACHE_PATH` và `HF_HOME`.

## Kiểm thử và đánh giá

```bash
uv run ruff check backend evals
uv run mypy backend/src
uv run pytest backend/tests -q                     # đặt TEST_POSTGRES_URL để chạy test PostgreSQL
npm --prefix frontend test
npm --prefix frontend run test:e2e                 # API giả lập
npm --prefix frontend exec playwright test -- --config playwright.live.config.ts   # giao diện + API + Gemini thật, tốn hạn mức

uv run python -m evals.harness.runner --agent oracle --gate       # không gọi LLM
uv run python -m evals.harness.runner --agent null                # phải trượt cổng chất lượng
uv run python -m evals.harness.runner --agent langgraph --gate    # gọi Gemini thật, tốn hạn mức
uv run python -m evals.harness.runner --agent langgraph --set holdout -k 3   # tập để dành, chỉ chạy khi chốt mốc
uv run --extra rerank python -m evals.retrieval.calibrate --check   # sau khi đổi điều khoản; --write để ghi ngưỡng mới
uv run python -m shopagent.cli validate-policies                    # kiểm kho chính sách, không cần DB
uv run --extra rerank python -m evals.retrieval.holdout           # đo retrieval, không gọi LLM
```

Mỗi lần chạy lưu quỹ đạo thô và bảng cổng chất lượng vào `evals/results/<run>/`. Ngưỡng cổng ở [evals/quality_gates.yaml](../evals/quality_gates.yaml). Harness ghi vào cơ sở dữ liệu riêng (`EVAL_DATABASE_URL`), không bao giờ vào cơ sở dữ liệu ứng dụng.

## Chụp lại ảnh giao diện

```bash
npm --prefix frontend run shots    # ghi vào docs/images/, dùng API giả lập, không cần backend
```

## Tập kịch bản để dành

`evals/scenarios_holdout/` chứa 16 kịch bản với tình huống và cách diễn đạt không có trong tập phát triển. Không sửa agent hay bộ chấm theo lỗi ở tập này; quy tắc đầy đủ ở [README của tập](../evals/scenarios_holdout/README.md). Oracle chỉ đạt 7/16 ở đây (nó dò từ khóa của tập phát triển), nên con số oracle 44/44 trên tập phát triển không chứng minh agent tổng quát được.

## Tuyên bố hoàn tất (S5)

Mỗi câu trả lời được đối chiếu với trạng thái cơ sở dữ liệu ngay sau lượt đó ([claims.py](../evals/harness/claims.py)): "đã hoàn tiền" cần một khoản hoàn `succeeded`, "đã hủy" cần một đơn `cancelled`, "đã tạo yêu cầu" cần một phiếu trả. Bộ phát hiện nhận các cách nói khác nhau và bỏ qua câu điều kiện, phủ định hoặc nói về tương lai; nó độc lập với bộ kiểm `grounding` của agent.
