# Thêm và sửa điều khoản chính sách

Kho chính sách có hai nguồn, gộp lại và kiểm tra cùng nhau trước khi lập chỉ mục:

| Nguồn | Dùng cho | Nơi viết |
|---|---|---|
| Điều khoản sinh tự động | quy tắc có con số (hạn đổi trả, phí, hạn mức duyệt) | `config/policy/rules.yaml`, mẫu ở `backend/src/shopagent/rag/generator.py` |
| Tài liệu Markdown | mọi thứ còn lại (bảo hành, FAQ, hướng dẫn) | `config/policy/docs/*.md`, mỗi file một điều khoản |

Phần có con số luôn lấy từ `rules.yaml`: đó là nguồn duy nhất mà engine nghiệp vụ cũng đọc, nên điều khoản và hành vi không thể lệch nhau.

## Viết một tài liệu

```markdown
---
clause_id: POL-WARRANTY-01          # POL-CHỦĐỀ-SỐ HAI CHỮ SỐ, duy nhất
topic: warranty
title: Bảo hành tai nghe
version: "2026-11-01"               # tùy chọn, mặc định là version của rules.yaml
effective_from: 2026-11-01          # tùy chọn
effective_to: null                  # tùy chọn; đặt khi có phiên bản mới thay thế
category_scope: [electronics_accessories]
parent_id: POL-WARRANTY-00          # tùy chọn: điều khoản mẹ khi cắt một văn bản dài thành nhiều phần
status: active                      # active (mặc định) | retired
---
Tai nghe được bảo hành mười hai tháng kể từ ngày mua. Lỗi do người dùng không được bảo hành.
```

## Quy tắc bị kiểm trước khi lập chỉ mục

`python -m shopagent.cli validate-policies` (không cần DB) liệt kê **mọi** vấn đề một lượt:

- mã điều khoản đúng dạng, không trùng (cùng mã và cùng phiên bản);
- nội dung không rỗng và không quá 1.200 ký tự (dài hơn thì cắt thành nhiều điều khoản có `parent_id`);
- `effective_to` sau `effective_from`; hai phiên bản của cùng một điều khoản không được cùng hiệu lực;
- mọi mã `POL-...` nhắc trong nội dung và mọi `parent_id` phải tồn tại.

## Lập chỉ mục

`python -m shopagent.cli index-policies` chỉ ghi lại điều khoản nào đổi nội dung (so băm nội dung), và chỉ tính embedding cho điều khoản đó. Điều khoản bị gỡ khỏi nguồn được đánh dấu `retired`, không xóa, nên lịch sử vẫn kiểm được.

Sau khi đổi nội dung: `uv run --extra rerank python -m evals.retrieval.calibrate --check`. Ngưỡng từ chối phụ thuộc vào văn bản điều khoản; lệch quá 0,03 thì chạy lại với `--write` và xem báo cáo holdout. Quy ước viết câu hỏi kiểm thử ở [evals/retrieval/README.md](../evals/retrieval/README.md).

## Khi kho lớn lên

Retriever có hai bước: nguồn ứng viên (`CandidateSource`, mặc định `HybridCandidates`: BM25 gộp theo hạng với BGE-M3) rồi reranker. Hiện kho có 10 điều khoản và reranker chấm hết, nên bước đầu chưa thể đổi thứ tự cuối; nó bắt đầu có tác dụng khi kho vượt số ứng viên của reranker (`retrieval.reranker.candidates`, hiện 10). Vector của từng điều khoản nằm trong cột `embedding` cùng tên model (`embedding_model`); `index-policies` chỉ embed điều khoản mới, đổi nội dung hoặc đổi model. Điều khoản nào chưa được embed bằng model đang cấu hình thì retrieval cảnh báo và lùi về BM25, không so vector khác model.

Khi kho đủ lớn để tính tương đồng trong Python chậm (hàng chục nghìn điều khoản), thay `HybridCandidates` bằng nguồn dùng pgvector; chỉ đổi một chỗ. Đo trước khi đổi: BGE-M3 đơn lẻ có Recall@4 thấp hơn BM25 trên kho 10 điều khoản (0,905 so với 0,973 trên tập độc lập), nó chỉ có ích khi gộp.

Số điều khoản tối đa một lần tra cứu trả về cho mô hình bị chặn theo tổng ký tự (`retrieval.max_result_chars` trong `config/app.yaml`); điều khoản xếp hạng thấp nhất bị bỏ nguyên, không bao giờ bị cắt giữa chừng.
