# Quy trình Đổi hàng (exchange)

1. Khách hàng yêu cầu đổi sang phân loại khác (kích cỡ, màu sắc):
   - Đổi hàng chỉ áp dụng cho cùng sản phẩm, khác phân loại, cùng tầm giá và mỗi sản phẩm chỉ được đổi 1 lần.
2. Kiểm tra tồn kho:
   - Gọi `check_variant_stock` với SKU phân loại mà khách muốn đổi.
   - Nếu hết hàng: Báo khách hết hàng và đề xuất chuyển sang giải pháp trả hàng hoàn tiền.
   - Nếu còn hàng:
     - Gọi `check_return_eligibility` với `resolution: "exchange"`.
3. Tạo đề xuất:
   - Gọi `propose_return` với `resolution: "exchange"` và mã `exchange_sku`.
   - Hướng dẫn khách bấm nút **Xác nhận** trên thẻ hành động để tạo phiếu gửi hàng đổi.
