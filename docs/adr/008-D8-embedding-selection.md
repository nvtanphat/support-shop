# ADR-008: Lựa chọn mô hình Embedding

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho lựa chọn mô hình embedding trong hệ thống shop-support-agent.

## Quyết định
Mô hình embedding tiếng Việt BGE-M3 chạy CPU hoặc API qua cổng EmbeddingProvider.

## Lý do và Đánh giá
Dưới 300 đoạn văn bản; chạy CPU cục bộ nhẹ và độc lập mạng.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.

## Cập nhật 2026-11-13: model và cách chạy thực tế

Không còn "cổng `EmbeddingProvider`": `rag/embeddings.py` nạp BGE-M3 qua fastembed (ONNX, CPU), bật/tắt bằng `retrieval.embedding.enabled` hoặc `RETRIEVAL_EMBEDDING_ENABLED`. Vector băm n-gram tự viết trước đây (không phải model ngôn ngữ) đã bị bỏ.

**Chọn bản int8** (`Xenova/bge-m3-int8`) làm mặc định thay cho bản đầy đủ (`BAAI/bge-m3`). Đo trên 58 câu hỏi của tập độc lập, mỗi bản trong một tiến trình riêng:

| | Đầy đủ (fp32) | int8 |
|---|---|---|
| Dung lượng tải | 2,27 GB | 0,57 GB |
| RAM sau khi nạp và embed | 1,77 GB | 1,14 GB |
| Tốc độ embed một câu hỏi | 47 ms | 27 ms |
| Cosine vector so với bản đầy đủ | 1 | 0,98 (nhỏ nhất 0,974) |
| Chỉ riêng bước vector, Recall@1 (42 câu có đáp án) | 0,738 | 0,714 |
| Chỉ riêng bước vector, Recall@4 | 0,881 | 0,881 |

Hai bản lệch nhau đúng một câu ở Recall@1 và giống hệt ở Recall@4. Xếp hạng top-1 trùng nhau ở 47/58 câu, nên "giống bản đầy đủ" không phải thước đo đúng; thước đo là độ chính xác so với đáp án chuẩn. Đổi sang bản đầy đủ chỉ cần sửa `retrieval.embedding.model` và chạy `index-policies`.

Điểm yếu đã biết của riêng bước vector: câu gõ không dấu và gõ sai chính tả (Recall@1 chỉ 1-2/6 mỗi loại). Đó là lý do BM25 và bước khôi phục dấu vẫn nằm trong bước gộp.
