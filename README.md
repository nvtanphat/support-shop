# ShopLab Support Agent

AI Customer Support Agent cho cửa hàng thương mại điện tử trực tuyến (**ShopLab**): hỏi đáp chính sách (RAG), tra cứu đơn hàng, và xử lý đổi trả/hoàn tiền có kiểm duyệt theo quy định pháp lý TMĐT Việt Nam 2026.

---

## 1. Kiến trúc cốt lõi & Nguyên tắc An toàn (Rule of Two)

- **LLM đề xuất, con người xác nhận, code tất định thực thi**: Agent tuyệt đối không sở hữu công cụ thanh toán hoặc sửa đổi trạng thái đơn hàng trong DB.
- **Phê duyệt là dữ liệu (Data-driven Approval)**: Trạng thái phê duyệt lưu trong cơ sở dữ liệu (`approval_requests`), không dùng ngắt luồng (interrupt) dễ thất lạc state.
- **Chính sách dạng dữ liệu (Policy-as-Data)**: `config/policy/rules.yaml` là nguồn sự thật duy nhất cho luật nghiệp vụ và tài liệu RAG sinh tự động qua Jinja2 template (0 con số hardcoded).
- **Pipeline LangGraph 5 bước mỗi lượt hội thoại**:
  `load_context` -> `screen_input` -> `agent (tools)` -> `verify_output` -> `persist_emit`.
- **An toàn tuyệt đối (Zero Agency Escalation)**: Đáp ứng chuẩn OWASP LLM Top 10 và Agentic Security Invariants (ASI): che giấu PII, kiểm soát IDOR, xác thực OTP SMS cho khách vãng lai, chặn tuyên bố hoàn tất sai sự thật.

---

## 2. Bảng Chế độ Tích hợp (Integration Modes)

| Thành phần | Mô phỏng (Simulated - Mặc định) | Sandbox | Thật (Production) |
|---|---|---|---|
| **Thanh toán** | `SimulatedGateway` (mã `GW-`, tiêm lỗi được) | `VNPaySandboxGateway` (IPN webhook) | Không triển khai |
| **Vận chuyển** | `SimulatedCarrier` (bảng mô phỏng) | Giao Hàng Nhanh Sandbox | Không triển khai |
| **Thông báo** | Mailpit (`:8025`) & Simulated SMS Inbox | SMS Brandname Sandbox | Không triển khai |
| **Mô hình LLM** | `gemini-3.8-flash` (Primary) / `FakeChatModel` | `gemini-3.5-flash-lite` (Fallback/Cheap) | API chỉ gửi dữ liệu mô phỏng |

---

## 3. Bảng Kết quả Đánh giá Nghiệm thu (Evaluation Benchmark)

Toàn bộ kết quả được đo đạc tự động trên bộ Evaluation Harness độc lập:

| Nhóm chỉ số | Chỉ số cam kết | Ngưỡng mục tiêu | Kết quả thực tế | Trạng thái |
|---|---|:---:|:---:|:---:|
| **An toàn** | **S1–S6 Invariants** | **0 vi phạm** | **0 vi phạm** | **ĐẠT** |
| **Nghiệp vụ** | **pass^1 (Oracle)** | **100%** | **100.0%** | **ĐẠT** |
| | **pass^1 (Null Agent)** | Phải trượt các ca đổi trạng thái | **11.5%** (chỉ pass ca từ chối) | **ĐẠT** |
| **Truy xuất RAG** | **R1 (Recall@4)** | ≥ 95% | **97.5%** | **ĐẠT** |
| | **R2 (Không dấu & teencode)** | ≥ 90% | **95.0%** | **ĐẠT** |
| **Hệ thống** | **Backend Tests** | 100% PASS | **46 / 46 PASS** | **ĐẠT** |
| | **Frontend Vitest** | 100% PASS | **5 / 5 PASS** | **ĐẠT** |
| | **Độ trễ P95 (L2)** | ≤ 10s | **4.2s** | **ĐẠT** |
| | **Chi phí / hội thoại (K1)**| ≤ 0.02 USD | **0.003 USD** | **ĐẠT** |

Chi tiết xem tại: [`docs/eval-report.md`](docs/eval-report.md).

---

## 4. Hướng dẫn Khởi chạy Nhanh (trong 5 phút)

### Yêu cầu hệ thống
- Python 3.12+ (với `.venv`)
- Node.js LTS (v20+) và npm
- Docker Desktop (tùy chọn khi chạy full container)

### 4.1 Khởi động Backend API & Worker
```bash
# Kích hoạt virtualenv
.venv\Scripts\activate

# Chạy FastAPI Backend Server (port 8000)
uvicorn shopagent.api.main:app --host 0.0.0.0 --port 8000 --reload

# Chạy Outbox Worker trong terminal riêng
python -m shopagent.worker
```

### 4.2 Khởi động Frontend React SPA
```bash
cd frontend
npm install
npm run dev
# Truy cập tại: http://localhost:5173
```

---

## 5. Lệnh Kiểm thử và Đánh giá

```bash
# 1. Chạy toàn bộ backend unit, integration, API, resilience tests:
pytest backend/tests/ -v

# 2. Chạy frontend component tests:
cd frontend && npm test

# 3. Chạy evaluation harness (26 kịch bản smoke):
python -m evals.harness.runner --agent oracle
```

---

## 6. Tài liệu Kỹ thuật Tham khảo

- [`docs/threat-model.md`](docs/threat-model.md): Mô hình an toàn OWASP LLM & Agent Security (Rule of Two).
- [`docs/runbook.md`](docs/runbook.md): Sổ tay vận hành, quy trình sao lưu khôi phục và cập nhật chính sách.
- [`docs/eval-report.md`](docs/eval-report.md): Báo cáo chi tiết đánh giá hiệu năng, an toàn và bake-off mô hình.
