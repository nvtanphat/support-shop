# Dữ liệu demo

Lệnh seed sinh 1.500 đơn ngẫu nhiên có thanh toán, vận đơn và lịch sử trả hàng, **cộng 24 đơn demo có mã cố định** (`SL-DEMO01`...) dựng theo mốc `--now`, mỗi đơn là một tình huống nghiệp vụ. Đơn nào cũng có ghi chú mô tả trong cột `note`. Tự động kiểm bằng [test_demo_seed.py](../backend/tests/unit/test_demo_seed.py).

| Nhóm | Đơn (khách `customer1` nếu không ghi) | Hành vi mong đợi |
|---|---|---|
| Hủy đơn | `SL-DEMO01` chưa thanh toán, `02` đã thanh toán, `03` đang đóng gói, `04` đang giao | `01`, `02` hủy tự phục vụ; `03` cần nhân viên duyệt; `04` không hủy được, xem hành trình |
| Hạn đổi trả | `06` giao 2 ngày, `07` giao 10 ngày, `08` giao 20 ngày | `06` đổi ý được, hoàn tự động; `07` quá hạn đổi ý (7 ngày) nhưng còn hạn nếu hàng lỗi (15 ngày); `08` quá mọi hạn |
| Loại trừ | `09` mỹ phẩm nguyên seal và đồ lót, `10` hàng thanh lý | Không đổi ý được |
| Bằng chứng và cổng duyệt | `11` điện thoại 6,49 triệu lỗi, `12` nhiều dòng có giảm giá | `11` cần ảnh, hoàn trên 2 triệu cần trưởng ca; `12` trả một phần, chia giảm giá |
| Đổi hàng | `13` áo cỡ M | Cỡ M còn hàng, cỡ L hết hàng |
| Hàng đợi nhân viên (`customer4`, `customer5`) | `14`, `16`, `18` | `RT-DEMO14` chờ duyệt cổng A; `RT-DEMO16` kho đã nhận, chờ kiểm; `RF-DEMO18` 6,49 triệu chờ trưởng ca (cổng B); ticket `TK-DEMO01` chờ nhân viên tiếp quản |
| Lịch sử hoàn tất | `15`, `17` | `RT-DEMO15` chờ khách gửi hàng; `RT-DEMO17` đã hoàn tiền `RF-DEMO17` |
| Cờ rủi ro | `19` (`customer2`), `20`-`23` (`customer3`) | `new_account_high_value`; `many_returns` |

`customer1` luôn có không quá 2 phiếu trả trong 30 ngày để cờ `many_returns` không bật và luồng hoàn tự động còn chạy được. Khách vãng lai tra đơn bằng mã đơn và số điện thoại (`customer1`: `0900000001`).

Tài khoản: khách `customer1@example.com` / `pass123`; nhân viên `agent@shop.vn`, `supervisor@shop.vn` / `staff123`; quản trị `admin@shop.vn` / `admin123`. Lệnh `seed` xóa và tạo lại toàn bộ bảng; chỉ dùng cho môi trường phát triển. Trên Windows đặt `PYTHONUTF8=1` để console in được tiếng Việt.
