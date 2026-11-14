# Quy trình Hủy Đơn hàng (cancel_order)

1. Tra cứu thông tin đơn hàng bằng `get_order`.
2. Kiểm tra trạng thái đơn:
   - Nếu `pending_payment` hoặc `confirmed`: Đơn đủ điều kiện tự phục vụ.
   - Nếu `packing`: Báo khách đơn đang được đóng gói nên yêu cầu hủy cần nhân viên kho xem xét duyệt.
   - Nếu `shipped` trở đi: Không thể hủy trực tiếp. Hướng dẫn khách từ chối nhận hàng khi shipper gọi hoặc làm thủ tục trả hàng sau khi nhận.
   - Nếu `cancelled` hoặc `completed`: Giải thích rõ trạng thái và từ chối.
   - Khi từ chối hủy, gọi `search_policy` về hủy đơn và trích dẫn mã điều khoản `[POL-...]` trong lời giải thích.
3. Khi đủ điều kiện hủy (hoặc xin duyệt hủy ở `packing`):
   - Gọi `propose_cancel_order` để tạo đề xuất.
   - Hướng dẫn khách hàng kiểm tra bản tóm tắt và nhấn nút **Xác nhận** trên thẻ hành động hiển thị trên màn hình.
   - Lưu ý: Không tự coi lời nói của khách trong chat là lệnh xác nhận hủy. Khách phải bấm nút xác nhận trên thẻ qua API an toàn.
