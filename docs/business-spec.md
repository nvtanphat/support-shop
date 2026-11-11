# Đặc Tả Nghiệp Vụ Shop Support Agent (Business Spec 2026)

Tài liệu này là nguồn sự thật bằng ngôn ngữ tự nhiên cho toàn bộ quy tắc nghiệp vụ, điều khoản chính sách, tính toán tài chính và máy trạng thái của `shop-support-agent`.
Bộ đánh giá độc lập (`evals/ground_truth/policy_decision_table.csv`) được dẫn xuất trực tiếp từ tài liệu này, không đọc từ cấu hình mã nguồn.

---

## 1. Trả Hàng và Đổi Hàng (Return & Exchange)

### 1.1 Khung thời gian và điều kiện cơ bản
- **Lỗi do cửa hàng / Sản phẩm lỗi (Shop Fault / Defect-like):**
  - Lý do: `defective` (lỗi nhà sản xuất), `damaged_in_transit` (hư hỏng do vận chuyển), `wrong_item` (giao sai hàng), `missing_item` (thiếu phụ kiện/quà), `not_as_described` (không đúng mô tả).
  - Thời hạn: Trong vòng **15 ngày** kể từ thời điểm giao hàng thành công (`delivered_at`).
  - Hạn chót: 23:59:59 giờ Việt Nam (`Asia/Ho_Chi_Minh`) của ngày `delivered_at + 15 ngày`.
  - Phí vận chuyển chiều về: Cửa hàng chịu (0 đ đối với khách).
  - Yêu cầu bằng chứng: Bắt buộc tối thiểu 2 hình ảnh rõ nét; riêng lý do `missing_item` yêu cầu video mở hộp (unboxing video).

- **Khách đổi ý (Customer Change of Mind):**
  - Lý do: `change_of_mind`.
  - Thời hạn: Trong vòng **7 ngày** kể từ thời điểm giao hàng thành công (`delivered_at`).
  - Hạn chót: 23:59:59 giờ Việt Nam (`Asia/Ho_Chi_Minh`) của ngày `delivered_at + 7 ngày`.
  - Phí vận chuyển chiều về: Khách chịu **30.000 đ** (trừ trực tiếp vào khoản hoàn tiền).
  - Tình trạng hàng: Chưa qua sử dụng, còn nguyên tem mác, hộp và phụ kiện.
  - Hàng hóa loại trừ (không áp dụng đổi trả do đổi ý):
    - `final_sale`: Hàng xả kho / giảm giá đặc biệt.
    - `hygiene`: Đồ lót, đồ bơi, tất/vớ.
    - `sealed_cosmetic`: Mỹ phẩm, sản phẩm chăm sóc cá nhân đã bóc niêm phong.
    - `personalized`: Hàng in/khắc theo yêu cầu cá nhân.

### 1.2 Thời hạn gửi trả hàng (Ship-back Deadline)
- Sau khi yêu cầu trả hàng được phê duyệt (`approved` hoặc tự động chấp nhận `awaiting_return`), khách có **5 ngày** để gửi hàng cho đơn vị vận chuyển.
- Nếu sau 5 ngày khách chưa gửi hàng, yêu cầu trả hàng tự động chuyển sang `expired`.

### 1.3 Quy trình Đổi hàng (Exchange)
- Chỉ áp dụng đổi sang cùng sản phẩm khác kích cỡ/màu sắc (variant) hoặc sản phẩm tương đương còn hàng trong kho (`stock > 0`).
- Nếu phân loại mới có giá cao hơn, khách thanh toán chênh lệch. Nếu thấp hơn, hoàn chênh lệch.
- Mỗi đơn hàng chỉ được đổi tối đa 1 lần. Nếu đã đổi một lần (`exchanged = true`), không cho đổi tiếp mà chỉ hỗ trợ trả hàng hoàn tiền nếu phát sinh lỗi mới.

---

## 2. Tính Toán Hoàn Tiền (Refund Calculation)

Mọi phép tính tiền tệ sử dụng số nguyên VND (`int`).

### 2.1 Phân bổ giảm giá cấp đơn (Order-level Discount Allocation)
- Khi đơn hàng có giảm giá tổng (`discount_total > 0`), giảm giá được phân bổ cho từng dòng sản phẩm theo tỷ lệ giá trị gộp (`qty * unit_price`):
  `line_discount = int((line_val * discount_total) / total_value)`
- Số tiền dư do làm tròn số nguyên được dồn cho dòng sản phẩm có giá trị lớn nhất, đảm bảo:
  `sum(line_discounts) == discount_total`

### 2.2 Số tiền hoàn cho từng món trả lại
- Giá trị hoàn trả cơ sở của dòng sản phẩm:
  `refund_base = (unit_price * returned_qty) - allocated_discount`
- Nếu lý do trả hàng là `change_of_mind`:
  `refund_amount = max(0, refund_base - 30000)` (trừ 30.000 đ phí vận chuyển).
- Nếu lý do thuộc lỗi cửa hàng (`defective`, v.v.):
  `refund_amount = refund_base` (không trừ phí vận chuyển).
- **Phí giao hàng ban đầu (`shipping_fee`):**
  - Chỉ được hoàn lại khi khách trả **toàn bộ đơn hàng** và nguyên nhân là lỗi của cửa hàng.
  - Trường hợp trả một phần hoặc trả do đổi ý: không hoàn phí giao hàng ban đầu.

### 2.3 Các ngưỡng phê duyệt hoàn tiền (Gate B)
- **Tự động duyệt (Auto-approve):** Số tiền hoàn `amount <= 500.000 đ` và không có cờ rủi ro (`risk_flags` rỗng).
- **Nhân viên duyệt (Agent role):** Số tiền hoàn `500.000 đ < amount <= 2.000.000 đ` hoặc có cờ rủi ro mức vừa.
- **Trưởng ca duyệt (Supervisor role):** Số tiền hoàn `amount > 2.000.000 đ` hoặc tài khoản có cờ rủi ro cao.

### 2.4 Phương thức hoàn tiền và SLA
- **Ví điện tử (E-wallet / VNPay):** Hoàn lại vào ví trong vòng 1-3 ngày làm việc.
- **Thẻ ngân hàng (Card):** Hoàn về thẻ trong vòng 7-15 ngày làm việc tùy ngân hàng phát hành.
- **Chuyển khoản (Bank Transfer):** Trong vòng 3-5 ngày làm việc sau khi nhận thông tin tài khoản thụ hưởng.
- **Đơn COD:** Sau khi kiểm tra hàng nhập kho đạt chuẩn, hệ thống gửi form an toàn cho khách điền số tài khoản ngân hàng thụ hưởng.

---

## 3. Hủy Đơn Hàng (Order Cancellation)

### 3.1 Điều kiện hủy
- Trạng thái `pending_payment` hoặc `confirmed`: Khách được tự phục vụ hủy ngay lập tức (`self-service`). Toàn bộ tiền đã thanh toán (nếu có) được tạo lệnh hoàn trả tự động.
- Trạng thái `packing` (đang đóng gói): Cần nhân viên kho hoặc trưởng ca duyệt (`cancel_packing`) để kiểm tra hàng đã rời băng chuyền đóng gói hay chưa.
- Trạng thái `shipped`, `out_for_delivery`, `delivered`: Không thể hủy đơn. Khách phải nhận hàng rồi thực hiện quy trình trả hàng.

---

## 4. Cờ Rủi Ro và Gian Lận (Risk Flags)

Hệ thống tự động kích hoạt cờ rủi ro khi phát hiện:
1. `many_returns`: Khách có từ 3 yêu cầu trả hàng trở lên trong vòng 30 ngày qua.
2. `high_return_rate`: Tỷ lệ trả hàng vượt quá 50% trong 10 đơn hàng gần nhất.
3. `new_account_high_value`: Tài khoản mới tạo dưới 7 ngày nhưng đặt đơn hàng có giá trị trên 2.000.000 đ và yêu cầu hoàn tiền ngay.

Khi có cờ rủi ro: Mọi yêu cầu trả hàng và hoàn tiền bắt buộc chuyển qua xét duyệt nhân viên (không tự động phê duyệt).

---

## 5. Bất Biến An Toàn Tuyệt Đối (Safety Invariants)

1. **S1 (Zero Agency Escalation):** Trợ lý AI chỉ ĐỀ XUẤT hành động (`propose_*`), KHÔNG BAO GIỜ tự xác nhận hoặc trực tiếp thay đổi trạng thái đơn, trả hàng hay hoàn tiền. Mọi tác vụ ghi đều yêu cầu khách bấm xác nhận qua API kèm `preview_hash`.
2. **S2 (Data Isolation / Anti-IDOR):** Khách hàng chỉ có quyền xem và thao tác trên đơn hàng thuộc quyền sở hữu của mình (`Principal.customer_id`). Khách vãng lai bắt buộc xác minh OTP qua số điện thoại đặt hàng.
3. **S3 (Approval Enforced):** Không khoản hoàn tiền nào được xử lý khi yêu cầu phê duyệt tương ứng chưa được nhân viên có thẩm quyền chấp thuận.
4. **S4 (No Double Refund):** Tổng số tiền hoàn của một đơn hàng không bao giờ được vượt quá số tiền thực tế khách đã trả (`paid_amount`).
5. **S5 (Verifiable Truth):** Trợ lý AI không được phát ngôn khẳng định "đã hoàn tất" (đã hủy đơn, đã hoàn tiền) khi hành động chưa được commit thành công trong cơ sở dữ liệu.
6. **S6 (Output Verification):** Mọi phát ngôn của trợ lý phải qua bộ lọc kiểm tra trích dẫn điều khoản hợp lệ và đối chiếu số liệu trước khi hiển thị cho người dùng.
