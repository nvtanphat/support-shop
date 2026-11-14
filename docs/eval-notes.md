## Bằng chứng và giới hạn của kết luận

Phần này viết tay; mọi con số ở trên được sinh từ artifact trong `evals/results/`.

- **Tập phát triển, Gemini thật** (64 kịch bản, k=1, mã `1b58e7f`): 64/64, mọi cổng đạt. Tập gồm cả các kịch bản trước là holdout (`H-*`, và `F-RET-07`, `F-SLOT-01`) đã được dùng để sửa agent, nên số này không chứng minh khả năng tổng quát.
- **Tập holdout `F-*`** (`evals/scenarios_holdout/`, chốt ở `3523daa` trước mọi sửa đổi agent, giữ nguyên làm kết quả lịch sử):
  - k=1, lần 1: 32/35; hai lỗi thật (`F-RET-07`, `F-SLOT-01`) được sửa qua dev, hai kịch bản chuyển sang dev và có kịch bản thay thế viết trước khi sửa.
  - k=1, lần 2: 34/35.
  - k=3 (mã `bade1bf`): 101/105, trượt cổng hỏi lại khi thiếu thông tin (14/15). Hai lỗi thật: liệt kê đủ hai đơn rồi vẫn hỏi dồn một đơn (`F-SLOT-06`, 1/3), và nhãn trạng thái của agent lệch với thẻ đơn (`F-ORD-01`, 3/3: agent gọi đơn đã gửi là "đang giao"). Không rút thêm kịch bản nào khỏi tập này; hai lỗi được sửa qua dev (`1b58e7f`) và đo trên tập mới dưới đây.
- **Tập nghiệm thu độc lập `G-*`** (`evals/scenarios_final/`, 21 kịch bản, commit `53da1bd` trước khi sửa hai lỗi trên), Gemini thật, k=3, mã `1b58e7f` (bảng "Independent final set" ở trên): **59/63 (93,7%); trượt cổng hỏi lại khi thiếu thông tin (14/15).** Bốn lần trượt:
  - `G-SLOT-01` lần 1: Gemini trả 503 UNAVAILABLE ("model đang quá tải") ba lần liên tiếp, lượt kết thúc bằng câu báo lỗi an toàn; agent không đoán đơn. Đây là lần trượt duy nhất của cổng này, do nhà cung cấp, nhưng vẫn được tính là trượt.
  - `G-RET-01` lần 1 và 2, `G-RET-05` lần 2: **lỗi thật của agent chưa sửa**. Khách nói hàng "chật" hoặc "mặc không vừa" và muốn trả lại; agent tự chuyển sang đổi size (hỏi size mới, hoặc gợi ý đổi phân loại) thay vì làm thủ tục trả hàng hoặc giải thích hàng loại trừ.
  - Cổng lộ dữ liệu khách khác là "chưa kiểm chứng" ở tập này vì tập không có kịch bản truy cập đơn của người khác; phần này được kiểm ở tập `F-*` (0/3, k=3) và ở nghiệm thu ứng dụng thật (S13).
- **Nghiệm thu ứng dụng thật** (`evals/e2e/live_acceptance.py`, 16 kịch bản qua HTTP API, PostgreSQL, Gemini và mô hình retrieval thật, mã `bade1bf`): 15/16 ở lần chạy liền; S12 trượt vì dữ liệu demo được seed theo mốc 11/11 nên đơn `SL-DEMO12` đã quá hạn đổi ý vào ngày chạy (agent từ chối đúng). Seed lại theo ngày chạy, S12 đạt. Playwright với API thật: 4/4.
- **Retrieval:** mã retrieval không đổi trong đợt này; bảng trên là lần đo lại trên cùng tập holdout retrieval (28 câu có đáp án, 20 câu ngoài phạm vi), khoảng tin cậy rộng. Với 10 điều khoản, bước lấy ứng viên hybrid (BM25 + BGE-M3) cho đúng số của BM25 + reranker vì reranker chấm hết cả kho. Số liệu chọn bản int8 và số ứng viên của reranker ở [ADR-008](adr/008-D8-embedding-selection.md) và [ADR-007](adr/007-D7-hybrid-rag.md).
- **Ảnh Docker** (2026-11-14): trước đây không build được (build context `./backend` không có `config/` và `pyproject.toml`); nay build từ gốc repo, 3,28 GB. Đã kiểm: retrieval trong container tắt mạng trả đúng điều khoản (mô hình đã nạp sẵn), migration và seed chạy bằng chính image, API trong container với PostgreSQL (`asyncpg` như `docker-compose.prod.yml`) sẵn sàng, đăng nhập, xem đơn, tạo cuộc trò chuyện, API duyệt của nhân viên. Chưa gửi tin nhắn chat qua container (cần Gemini).
- **Chưa kiểm chứng:** tải đồng thời với Gemini thật, và thời gian phản hồi trên phần cứng khác.
