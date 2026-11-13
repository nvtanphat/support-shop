# Sổ tay Vận hành Hệ thống (Runbook) — Shop Support Agent

> Hướng dẫn vận hành, giám sát, khắc phục sự cố và quy trình bảo trì cho hệ thống Shop Support Agent.

---

## 1. Khởi động và Dừng dịch vụ

### 1.1 Khởi động toàn bộ cụm dịch vụ qua Docker Compose
```bash
# Khởi động ở chế độ background
docker compose up -d

# Xem log các dịch vụ
docker compose logs -f api worker postgres phoenix
```

### 1.2 Kiểm tra trạng thái sức khỏe
```bash
# Liveness probe
curl -f http://localhost:8000/healthz

# Readiness probe (kiểm tra kết nối DB và bộ nhớ cache)
curl -f http://localhost:8000/readyz

# Phiên bản hệ thống
curl -f http://localhost:8000/version
```

### 1.3 Dừng và Khởi động lại Graceful
```bash
# Dừng an toàn (worker hoàn thành batch hiện tại trước khi thoát)
docker compose down
```

---

## 2. Sao lưu và Khôi phục Dữ liệu (Backup & Disaster Recovery)

### 2.1 Sao lưu cơ sở dữ liệu hàng đêm
```bash
# Tạo bản dump PostgreSQL có nén và timestamp
docker exec -t shopagent-postgres pg_dump -U postgres -d shopagent -F c -b -v -f /var/lib/postgresql/data/backup_$(date +%Y%m%d_%H%M%S).dump
```

### 2.2 Diễn tập Khôi phục Dữ liệu (Restore Drill)
```bash
# 1. Ngắt kết nối API và Worker
docker compose stop api worker

# 2. Xóa và tạo lại database đích
docker exec -i shopagent-postgres psql -U postgres -c "DROP DATABASE IF EXISTS shopagent_restore;"
docker exec -i shopagent-postgres psql -U postgres -c "CREATE DATABASE shopagent_restore;"

# 3. Phục hồi từ file backup
docker exec -i shopagent-postgres pg_restore -U postgres -d shopagent_restore /var/lib/postgresql/data/backup_target.dump

# 4. Xác minh tính toàn vẹn (chạy cli verify-data)
docker compose run --rm api python -m shopagent.cli verify-data
```

---

### 2.3 Script vận hành (`ops/`)

`ops/backup.sh`, `ops/restore.sh <dump>`, `ops/deploy.sh <tag>`, `ops/rollback.sh` bọc các lệnh Docker Compose ở trên. Mới kiểm tra cú pháp bằng `bash -n`, chưa chạy trên máy chủ thật; diễn tập sao lưu, khôi phục và quay lui trước khi dựa vào chúng. Rollback không hoàn tác migration.

---

## 3. Quy trình Cập nhật Chính sách Cửa hàng (Policy Update Workflow)

Khi cửa hàng cập nhật quy định đổi trả/hủy đơn:

1. **Cập nhật quy tắc nguồn:** Chỉnh sửa file `config/policy/rules.yaml` (ví dụ: đổi `windows_days` hoặc `return_shipping`).
2. **Sinh lại văn bản chính sách Markdown:**
   ```bash
   python -m shopagent.rag.generator
   ```
3. **Đánh chỉ mục lại vào Policy Chunks (RAG):**
   ```bash
   python -m shopagent.cli index-policies
   ```
4. **Kiểm tra hồi quy:**
   ```bash
   pytest backend/tests/unit/test_policy_rag.py -v
   pytest backend/tests/unit/test_policy_table_against_engine.py -v
   ```

---

## 4. Xử lý Sự cố Khẩn cấp (Troubleshooting & Emergency)

### 4.1 Tiến trình Worker bị treo hoặc bản ghi Outbox kẹt
**Triệu chứng:** Thẻ hành động hiển thị "Đang xử lý hoàn tiền..." quá 5 phút.
**Khắc phục:**
1. Kiểm tra hàng chờ `outbox_events`:
   ```sql
   SELECT id, type, status, attempts, next_attempt_at FROM outbox_events WHERE status = 'pending';
   ```
2. Khởi động lại worker:
   ```bash
   docker compose restart worker
   ```
3. Tác vụ `PaymentReconciler` sẽ tự động đối soát các khoản hoàn tiền kẹt với Cổng thanh toán sau 5 phút và cập nhật trạng thái `succeeded`.
