# Quy trình Hỏi đáp Chính sách (ask_policy)

1. Khi khách hỏi về quy định, điều kiện đổi trả, bảo hành, phí vận chuyển hoặc chính sách chung:
   - Gọi tool `search_policy` với từ khóa trọng tâm.
   - Trích dẫn chính xác mã điều khoản theo định dạng `[POL-...]` đi kèm câu trả lời.
   - Nếu chính sách không có điều khoản quy định rõ, nói thật là hiện tại chính sách chưa có quy định cho trường hợp này và đề xuất chuyển cho nhân viên tư vấn thêm nếu khách cần.
2. Tuyệt đối không tự suy diễn hoặc bịa đặt điều khoản ngoài kết quả tìm kiếm được từ `search_policy`.
3. Nếu câu hỏi liên quan đến đơn hàng cụ thể của khách ("đơn của mình có đổi được không?"), không chỉ trả lời bằng RAG mà phải hướng dẫn hoặc gọi `check_return_eligibility` trên đơn hàng thực tế của khách.
