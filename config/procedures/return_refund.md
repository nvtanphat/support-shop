# Quy trình Yêu cầu Trả hàng và Hoàn tiền (return_refund)

1. Thu thập thông tin từ khách:
   - Mã đơn hàng (tra cứu qua `get_order` để lấy đúng danh sách `item_id`).
   - Món hàng muốn trả (`item_ids`).
   - Lý do trả hàng (mã chuẩn: `defective`, `damaged_in_transit`, `wrong_item`, `missing_item`, `not_as_described`, `change_of_mind`).
   - Tình trạng bao bì và hàng hóa.
2. Kiểm tra điều kiện:
   - Gọi `check_return_eligibility`.
   - Nếu không đủ điều kiện (quá hạn 7 ngày đổi ý, hàng loại trừ đồ lót/vệ sinh cá nhân hygiene, hàng final_sale, mở niêm phong mỹ phẩm...): BẮT BUỘC gọi `search_policy` tra cứu và trích dẫn rõ mã điều khoản tương ứng (ví dụ `[POL-RETURN-02]` cho đổi ý quá 7 ngày, `[POL-RETURN-03]` cho danh mục loại trừ đồ lót/vệ sinh cá nhân).
   - Nếu đủ điều kiện:
     - Nêu rõ số tiền hoàn ước tính (đã trừ phí chiều về 30.000 đ nếu đổi ý, hoặc phân bổ giảm giá nếu có voucher).
     - Nêu rõ nếu lý do yêu cầu bằng chứng (ảnh/video).
3. Tạo đề xuất:
   - Gọi `propose_return` với `resolution: "refund"`.
   - Nhắc khách bấm nút **Xác nhận** trên thẻ đề xuất và tải ảnh bằng chứng qua biểu mẫu (nếu cần).
   - Tuyệt đối không tuyên bố "đã hoàn tiền xong" trong khi yêu cầu mới đang ở bước đề xuất hoặc chờ duyệt/chờ hàng trả về.
