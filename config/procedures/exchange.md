# Quy trình Đổi hàng (exchange)

1. Khách hàng yêu cầu đổi sang phân loại khác (kích cỡ, màu sắc):
   - Đổi kích cỡ (size) hoặc màu sắc thuộc chính sách đổi hàng `POL-EXCHANGE-01` áp dụng trong thời hạn 15 ngày theo chính sách đổi trả `POL-RETURN-01`.
   - Luôn gọi `search_policy` với từ khóa "đổi size đổi hàng" và trích dẫn mã điều khoản quy định `[POL-RETURN-01]` cùng `[POL-EXCHANGE-01]`.
   - Giới hạn số lần đổi: Mỗi sản phẩm chỉ được hỗ trợ đổi tối đa 1 lần duy nhất. Nếu khách hỏi đã đổi 1 lần có đổi tiếp được không, BẮT BUỘC gọi `search_policy` và trích dẫn `[POL-RETURN-01]` giải thích quy định chỉ hỗ trợ đổi tối đa 1 lần.
   - Đổi hàng chỉ áp dụng cho cùng sản phẩm, khác phân loại, cùng tầm giá trong 15 ngày.
2. Kiểm tra tồn kho:
   - Gọi `check_variant_stock` với SKU phân loại mà khách muốn đổi.
   - Nếu hết hàng: Báo khách hết hàng và đề xuất chuyển sang giải pháp trả hàng hoàn tiền.
   - Nếu còn hàng:
     - Gọi `check_return_eligibility` với `resolution: "exchange"`.
3. Tạo đề xuất:
   - Gọi `propose_return` với `resolution: "exchange"` và mã `exchange_sku`.
   - Hướng dẫn khách bấm nút **Xác nhận** trên thẻ hành động để tạo phiếu gửi hàng đổi.
