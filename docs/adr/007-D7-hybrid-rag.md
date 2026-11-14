# ADR-007: RAG lai trên Postgres

- **Trạng thái:** Đã chấp thuận (Accepted)
- **Ngày quyết định:** 2026-11-11
- **Phạm vi:** shop-support-agent

## Bối cảnh và Vấn đề
Cần đưa ra quyết định kiến trúc chuẩn xác cho rag lai trên postgres trong hệ thống shop-support-agent.

## Quyết định
pgvector kết hợp full-text unaccent, trộn bằng RRF.

## Lý do và Đánh giá
Tiếng Việt cần khớp cả ngữ nghĩa và từ khóa không dấu; không cần thêm database ngoài.

## Hệ quả
Quyết định này được áp dụng xuyên suốt mã nguồn, bộ test và tài liệu hệ thống.

## Cập nhật 2026-11-13: cài đặt thực tế

Quyết định gốc (pgvector + full-text trong PostgreSQL) **chưa được cài đặt** và chưa cần: kho có 10 điều khoản, nên toàn bộ tính điểm chạy trong tiến trình. Cài đặt hiện tại:

- Bước 1, lấy ứng viên (`HybridCandidates`): BM25 trên văn bản bỏ dấu, gộp theo hạng (RRF, k=60) với độ tương đồng vector BGE-M3. BM25 là cổng: không từ nào khớp thì trả "không có bằng chứng", vì model vector luôn tìm ra một điều khoản gần nhất.
- Bước 2: cross-encoder `bge-reranker-v2-m3` xếp hạng lại tối đa 10 ứng viên; điểm tốt nhất dưới ngưỡng thì từ chối.
- Vector lưu ở cột `embedding` kèm `embedding_model`; đổi model thì `index-policies` embed lại, và retrieval lùi về BM25 thay vì so vector khác model.

**Đã đo và không đổi:** số ứng viên của reranker. Trên cả hai tập câu hỏi (ngưỡng hiệu chỉnh riêng cho từng cấu hình):

| Ứng viên | Giây mỗi truy vấn | Holdout Recall@1 | Holdout Recall@4 | Từ chối câu ngoài phạm vi |
|---|---|---|---|---|
| 10 (đang dùng) | 2,07 | 0,929 | 0,982 | 100% |
| 6 | 1,09 | 0,857 | 0,964 | 100% |
| 4 | 0,78 | 0,929 | 1,000 | 95% (lọt 1/20) |

Giảm xuống 4 nhanh hơn 1,3 giây nhưng làm lọt một câu ngoài phạm vi; kết quả không đơn điệu (6 tệ hơn 4) nên mẫu 48 câu quá nhỏ để tin vào khác biệt. Giữ 10: không đánh đổi tính chất an toàn lấy 1,3 giây.

**Khi nào làm pgvector:** khi tính tương đồng trong Python chậm (hàng chục nghìn điều khoản). Chỉ cần thay `HybridCandidates` bằng nguồn ứng viên khác (`CandidateSource`).
