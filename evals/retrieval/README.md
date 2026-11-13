# Bộ câu hỏi đo retrieval

Hai tập câu hỏi cho kho chính sách:

| File | Dùng để | Quy tắc |
|---|---|---|
| `policy_queries_independent.yaml` | chọn ngưỡng từ chối, so sánh phương án | được dùng khi chỉnh retrieval |
| `policy_queries_holdout.yaml` | báo cáo cuối | viết sau tập kia, **chỉ chấm với ngưỡng đã chốt**, không dùng để chỉnh gì |

## Viết một câu hỏi mới

```yaml
- {id: P20, kind: paraphrase, split: test, q: "Đặt nhầm size thì xử lý sao?", expected: [POL-EXCHANGE-01]}
- {id: O30, kind: out_of_domain, near_topic: true, split: test, q: "Bảo hành tai nghe mấy tháng?", expected: []}
```

- `expected`: các điều khoản **cùng nhau** trả lời được câu hỏi, quyết định theo ý nghĩa nghiệp vụ, không theo từ ngữ của điều khoản. Rỗng nghĩa là chính sách không nói về việc này và hệ thống phải từ chối.
- `kind`: `paraphrase`, `slang`, `typo`, `unaccented`, `multi_intent`, `temporal`, `out_of_domain`.
- Viết câu hỏi **như khách nhắn tin**, không chép lại câu chữ của điều khoản. Câu hỏi chép nguyên văn điều khoản thì tập nào cũng đạt và không đo được gì.

## Câu ngoài phạm vi "sát chủ đề" (`near_topic: true`)

Đây là loại dễ lọt nhất: nghe như chính sách của shop nhưng kho không có đáp án (bảo hành, trả góp, đại lý, mã giảm giá). Câu như "thời tiết hôm nay" bị từ chối rất dễ nên không chứng minh gì. Khi thêm điều khoản mới, **thêm cả những câu sát chủ đề của nó mà kho vẫn chưa trả lời được**: chính các câu đó cho biết ngưỡng còn đúng hay không.

Tối thiểu 20% câu `out_of_domain` phải có `near_topic: true` (test kiểm).

## Mỗi lần thêm hoặc sửa điều khoản

1. `python -m shopagent.cli validate-policies` (kiểm dữ liệu, không cần DB).
2. Viết câu hỏi cho điều khoản mới: ít nhất 3 câu có đáp án (một paraphrase, một slang hoặc không dấu, một sát với điều khoản dễ nhầm) và 2 câu sát chủ đề không có đáp án.
3. `python -m shopagent.cli index-policies` (chỉ ghi lại điều khoản đổi).
4. `uv run --extra rerank python -m evals.retrieval.calibrate --check`. Lệch quá 0,03 thì chạy lại với `--write`, rồi xem holdout.
5. Thêm một điều khoản làm lệch thống kê BM25 của cả kho (đã xảy ra khi thử `POL-RETURN-05`): benchmark phải đạt lại ngưỡng trước khi gộp.
