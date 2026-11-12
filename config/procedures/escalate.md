# Quy trình Chuyển giao Nhân viên (escalate)

1. Khi nào kích hoạt chuyển giao cho nhân viên:
   - Khách hàng yêu cầu trực tiếp gặp người hỗ trợ.
   - 2 lần liên tiếp bot không hiểu hoặc không giải quyết được vấn đề của khách.
   - Sự cố an toàn sản phẩm (cháy nổ, gây thương tích dị ứng nặng) -> Mức độ khẩn cấp (urgent).
   - Tranh chấp thanh toán, bị trừ tiền 2 lần, khiếu nại bồi thường phức tạp.
   - BẮT BUỘC: Khi khách báo bị trừ tiền hai lần hoặc có tranh chấp thanh toán, BẮT BUỘC gọi ngay tool `escalate_to_human(reason_code="customer_request", summary="...")` ngay trong lượt đó. Hệ thống chỉ ghi nhận chuyển nhân viên khi có Tool Call này. TUYỆT ĐỐI KHÔNG chỉ nói "mình sẽ chuyển" hoặc "đang chuyển" bằng lời nói mà không gọi tool!
   - Yêu cầu xuất hóa đơn VAT, sửa hóa đơn.
   - Yêu cầu xem, chỉnh sửa hoặc xóa dữ liệu cá nhân (GDPR/Luật Bảo vệ Dữ liệu Cá nhân).
   - Đơn mua qua sàn thương mại điện tử (Shopee, TikTok Shop) sau khi đã giải thích kênh của sàn mà khách vẫn cần nhân viên hỗ trợ.
2. Thực hiện:
   - Gọi tool `escalate_to_human` với `reason_code` và bản `summary` súc tích, khách quan.
   - Thông báo cho khách hàng mã phiếu hỗ trợ và thời gian phản hồi dự kiến của chuyên viên chăm sóc khách hàng (trong vòng 30 phút).
   - Khi hội thoại đã chuyển sang chế độ nhân viên, bot dừng phản hồi và nhường luồng chat cho nhân viên hỗ trợ.
