# Chế độ tích hợp

`INTEGRATION_MODE` (mặc định `simulated`) quyết định các cổng ra ngoài chạy thật hay giả lập. Giao diện hiển thị biểu ngữ môi trường theo giá trị này.

| Cổng | Cổng trừu tượng | Mô phỏng (`simulated`) | Sandbox / thật |
|---|---|---|---|
| Thanh toán, hoàn tiền | `infra/payments/port.py` | `SimulatedPaymentGateway`: idempotent theo khóa, có thể chèn lỗi một lần | Chưa có |
| Vận chuyển | `infra/carriers/port.py` | Dữ liệu vận đơn trong DB, tiến bằng `POST /sandbox/shipments/{code}/advance` | Chưa có |
| OTP khách vãng lai | `infra/otp/port.py` | OTP trả về trong phản hồi (`simulated_otp`), không gửi SMS | Chưa có |
| Thông báo | `infra/notifications/port.py` | Sự kiện SSE trong ứng dụng | SMTP chưa có |
| LLM | `infra/llm/factory.py` | `fake` dùng cho test | Gemini (cần `GEMINI_API_KEY`) |

## Điều khiển chỉ có ở chế độ mô phỏng

Chỉ mount khi `INTEGRATION_MODE=simulated`, và chỉ vai trò `admin`:

- `POST /sandbox/shipments/{tracking_code}/advance`: đẩy vận đơn một bước (shipped, in_transit, out_for_delivery, delivered).
- `POST /sandbox/payments/fail-next`: lần hoàn tiền kế tiếp thất bại một lần, để thử thử lại và đối soát. Cổng giả lập dùng chung một thể hiện trong tiến trình; worker chạy ở tiến trình khác nên không thấy cờ này.
- `POST /sandbox/clock`: cố định hoặc thả đồng hồ ứng dụng.

## Giới hạn hiện tại

Chưa có adapter VNPay sandbox, `POST /webhooks/vnpay/ipn`, SMS thật hay SMTP. Chạy production với `simulated` chỉ có ý nghĩa trình diễn: tiền không di chuyển.
