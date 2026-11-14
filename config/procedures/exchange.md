# Quy trình Đổi hàng (exchange)

1. Khi nào là đổi hàng:
   - Chỉ khi khách nói muốn đổi sang phân loại khác ("đổi sang size L", "đổi màu khác", "đổi cái khác"), hoặc trả lời đồng ý khi được hỏi có muốn đổi không.
   - Hàng chật, rộng, không vừa mà khách nói muốn **trả** là trả hàng hoàn tiền (lý do đổi ý), không phải đổi size. Không tự chuyển yêu cầu trả hàng thành đổi hàng. Nếu khách chưa nói muốn trả hay đổi, hỏi một câu: trả hàng hoàn tiền hay đổi sang size khác.
2. Điều kiện đổi hàng: tra cứu `search_policy` (chính sách đổi hàng) và trích dẫn điều khoản trả về; thời hạn và điều kiện lấy từ điều khoản và từ `check_return_eligibility`, không tự nêu con số. Đổi hàng chỉ sang cùng sản phẩm, khác phân loại, cùng giá, mỗi sản phẩm đổi tối đa một lần.
3. Kiểm tra tồn kho:
   - Gọi `check_variant_stock` với SKU sản phẩm khách đang có để xem các phân loại khác.
   - Không có phân loại khách muốn, hoặc hết hàng: nói rõ và đề nghị trả hàng hoàn tiền.
   - Có hàng: gọi `check_return_eligibility` với `resolution: "exchange"`.
4. Tạo đề xuất:
   - Gọi `propose_return` với `resolution: "exchange"` và `exchange_sku` lấy từ kết quả `check_variant_stock`.
   - Hướng dẫn khách bấm nút **Xác nhận** trên thẻ hành động để tạo phiếu gửi hàng đổi.
