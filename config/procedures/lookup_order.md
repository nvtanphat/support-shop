# Quy trình Tra cứu Đơn hàng (lookup_order)

1. Đối với khách hàng đã đăng nhập:
   - Nếu khách không nêu mã đơn cụ thể, gọi `list_my_orders` để hiển thị danh sách đơn gần nhất cho khách chọn.
   - Nếu khách cung cấp mã đơn (hoặc chỉ định một đơn cụ thể), gọi `get_order` để lấy chi tiết mốc thời gian, trạng thái và các hành động khả dụng.
   - Nếu khách hỏi vị trí đơn đang giao hoặc quá trình vận chuyển, gọi `track_shipment`.
2. Đối với khách hàng vãng lai (chưa đăng nhập):
   - Gọi `lookup_order_guest` với mã đơn.
   - Nếu hệ thống trả về `GUEST_VERIFICATION_REQUIRED`, thông báo khách hàng mở biểu mẫu xác minh để nhập số điện thoại và nhận OTP bảo mật trước khi tra cứu.
3. Luôn bảo đảm dữ liệu cá nhân (số điện thoại, địa chỉ cụ thể) được che để bảo vệ quyền riêng tư.
