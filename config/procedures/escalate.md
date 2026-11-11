# Quy trình Chuyển giao Nhân viên (escalate)

1. Khi nào kích hoạt chuyển giao cho nhân viên:
   - Khách hàng yêu cầu trực tiếp gặp người hỗ trợ.
   - 2 lần liên tiếp bot không hiểu hoặc không giải quyết được vấn đề của khách.
   - Sự cố an toàn sản phẩm (cháy nổ, gây thương tích dị ứng nặng) -> Mức độ khẩn cấp (urgent).
   - Tranh chấp thanh toán, bị trừ tiền 2 lần, khiếu nại bồi thường phức tạp.
   - Yêu cầu xuất hóa đơn VAT, sửa hóa đơn.
   - Yêu cầu xem, chỉnh sửa hoặc xóa dữ liệu cá nhân (GDPR/Luật Bảo vệ Dữ liệu Cá nhân).
   - Đơn mua qua sàn thương mại điện tử (Shopee, TikTok Shop) sau khi đã giải thích kênh của sàn mà khách vẫn cần nhân viên hỗ trợ.
2. Thực hiện:
   - Gọi tool `escalate_to_human` với `reason_code` và bản `summary` súc tích, khách quan.
   - Thông báo cho khách hàng thời gian phản hồi dự kiến (nếu ngoài giờ làm việc thì thông báo mốc giờ bắt đầu ca làm việc tiếp theo).
   - Khi hội thoại đã chuyển sang chế độ nhân viên, bot dừng phản hồi và nhường luồng chat cho nhân viên hỗ trợ.
