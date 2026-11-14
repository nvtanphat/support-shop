# Mô hình Đe dọa An toàn (Threat Model) — Shop Support Agent

> Tài liệu tuân thủ chuẩn OWASP Top 10 for LLM Applications, Agentic Security Invariants (ASI), và nguyên tắc cốt lõi **"Rule of Two"**.

---

## 1. Nguyên lý Thiết kế An toàn Cốt lõi: Rule of Two

Trong hệ thống AI Agentic tự trị, nguy cơ lớn nhất là khi một Agent đồng thời sở hữu 3 đặc tính:
1. **(A) Đọc đầu vào không tin cậy:** Tin nhắn người dùng, ghi chú đơn hàng, nội dung tệp đính kèm, tài liệu tra cứu.
2. **(B) Truy cập dữ liệu nhạy cảm:** Thông tin đơn hàng của khách, thông tin thanh toán, địa chỉ, số điện thoại.
3. **(C) Quyền thay đổi trạng thái (State-changing agency):** Quyền hủy đơn, hoàn tiền, đổi hàng, sửa đổi cơ sở dữ liệu.

### Biện pháp cách ly bắt buộc
Để loại bỏ nguy cơ Agent bị tấn công Prompt Injection dẫn đến chiếm quyền điều khiển hệ thống và bòn rút tiền/dữ liệu:
- **Shop Support Agent CHỈ sở hữu thuộc tính (A) và (B).**
- **Thuộc tính (C) bị LOẠI BỎ HOÀN TOÀN khỏi Agent.**

```
[Khách hàng] ──► (Tin nhắn không tin cậy) ──► [Agent Node] (Chỉ Đọc & Đề xuất)
                                                     │
                                                     ▼
                                            [Thẻ Đề xuất (PendingAction)]
                                                     │
[Khách hàng xác thực] ──(Bấm nút)──► POST /actions/{id}/confirm (preview_hash)
                                                     │
                                                     ▼
                                            [Service Nghiệp vụ Tất định]
                                            (Tính toán lại điều kiện & Transaction)
                                                     │
                                                     ▼
                                            [Outbox Worker] ──► [Cổng Thanh toán]
```

---

## 2. Ma trận Mối đe dọa và Biện pháp Phòng vệ (OWASP & ASI)

| Mã | Mối đe dọa | Phân loại OWASP / ASI | Biện pháp kỹ thuật | Bất biến đảm bảo |
|---|---|---|---|---|
| **TH-01** | Chèn lệnh trực tiếp qua chat để ép hoàn tiền | LLM01, ASI01, ASI02 | Agent không có công cụ thanh toán/hoàn tiền; chỉ tạo bản ghi `pending_actions`; khách phải tự bấm xác nhận qua API riêng. | **S1, S3** |
| **TH-02** | Chèn lệnh gián tiếp (Indirect Prompt Injection) qua ghi chú đơn hàng hoặc tên sản phẩm | LLM01, ASI01 | Dữ liệu người dùng tự do được gói trong trường `untrusted_text` và cắt ngắn; tài liệu chính sách được nạp từ kho sinh nội bộ. | **S1, S5** |
| **TH-03** | Khai thác IDOR xem đơn hàng hoặc yêu cầu đổi trả của khách khác | ASI03, LLM02 | Phiên gọi API tiêm `Principal` xác thực; mọi câu lệnh SQL đều gắn điều kiện `customer_id == principal.customer_id`; Row-Level Security. | **S2** |
| **TH-04** | Giả danh quyền hạn ("Tôi là quản trị viên/quản lý cửa hàng") | ASI09 | Quyền hạn chỉ được xác định qua JWT Claims đã được ký bằng bí mật HMAC-SHA256, tuyệt đối không lấy vai trò từ nội dung prompt/chat. | **S1, S3** |
| **TH-05** | Agent tự động xác nhận thay cho khách hàng | ASI02 | Không có tool xác nhận; API `POST /actions/{id}/confirm` bắt buộc `preview_hash` khớp chính xác dữ liệu đã hiển thị cho khách xem. | **S1** |
| **TH-06** | Dò quét mã đơn hàng của khách vãng lai | ASI03, LLM02 | Mã định danh đơn hàng ngẫu nhiên Crockford Base32 (1 tỷ tổ hợp); yêu cầu xác thực OTP SMS tới số điện thoại đặt hàng; Rate-limit IP/đơn/sđt. | **S2** |
| **TH-07** | Phát ngôn giả mạo hoặc chưa kiểm chứng (Hallucination) | LLM07 | Mọi tin nhắn trợ lý phải qua node `verify_output`: kiểm tra trích dẫn hợp lệ `[POL-...]`, kiểm tra nguồn gốc số tiền/số ngày, chặn tuyên bố đã hoàn tiền giả. | **S5, S6** |
| **TH-08** | Tấn công từ chối dịch vụ hoặc tiêu tốn ngân sách LLM | LLM06 | Giới hạn vòng lặp tool (`max_iterations = 6`); giới hạn ngân sách hội thoại (0.10 USD); Kill-switch ngắt hệ thống khi vượt ngân sách ngày. | **K1, K2** |
| **TH-09** | Tải lên tệp độc hại (Webshell, mã độc) | Web Security | Kiểm tra Magic Bytes, chỉ cho phép ảnh JPG/PNG/WEBP và video MP4; dung lượng tối đa 10MB; lưu trữ ngoài web root bằng tên file SHA256. | — |
| **TH-10** | Tranh chấp race-condition / Hoàn tiền trùng lặp (Double Refund) | Financial Security | Idempotency Key trên mọi request ghi; cơ chế khóa hàng `SELECT FOR UPDATE` và ràng buộc cơ sở dữ liệu `UNIQUE(order_id)` cho hoàn tiền. | **S4** |

---

## 3. Quản lý Dữ liệu Cá nhân (PII)

1. **Che giấu (Masking):** Số điện thoại hiển thị dạng `*******567`; địa chỉ hiển thị dạng `***, Phường Bến Nghé, Quận 1, TP. HCM`.
2. **Không đưa vào LLM:** Số thẻ ngân hàng, số CCCD/CMND, mật khẩu. Nếu khách hàng nhập số thẻ vào chat, node `screen_input` sẽ che giấu trước khi đưa vào lịch sử hội thoại.
3. **Thời gian lưu trữ (Data Retention):** Hội thoại và checkpoint LangGraph được ẩn danh hóa sau 180 ngày; tệp bằng chứng được tự động dọn dẹp sau 90 ngày đóng ca.
