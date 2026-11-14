# AGENTS.md — Quy tắc làm việc cho AI Coding Agent

> Áp dụng cho toàn bộ repository `shop-support-agent`.
> Mục tiêu: xây dựng AI Application end-to-end **đúng nghiệp vụ, dễ hiểu, dễ bảo trì, có thể kiểm chứng**, không tích lũy code rác sau mỗi lần sửa.

## 1. Nguồn sự thật và cách ra quyết định

- Đọc `SHOP_SUPPORT_AGENT_IMPLEMENTATION_PLAN_2026.md`, `README.md`, các ADR liên quan và code hiện hữu **trước khi sửa**. Không suy diễn rằng kế hoạch đã được triển khai trong code.
- Khi thông tin mâu thuẫn, ưu tiên: **an toàn và tính đúng nghiệp vụ → yêu cầu hiện tại → ADR/quyết định đã chốt → kế hoạch triển khai → cách làm sẵn có**. Ghi rõ mâu thuẫn nếu phải thay đổi thiết kế.
- Làm tới sản phẩm hoàn chỉnh theo kế hoạch; không tự thu hẹp phạm vi thành MVP, nhưng cũng **không tự thêm tính năng, service hoặc framework không cần thiết**.
- Tự giải quyết các quyết định kỹ thuật thông thường bằng cách kiểm tra code, test và tài liệu. Chỉ hỏi khi thiếu dữ kiện có thể gây hậu quả không thể đảo ngược hoặc thay đổi nghiệp vụ đáng kể.
- Không giả vờ đã chạy test, đã kiểm chứng, đã deploy hoặc đã có benchmark. Phân biệt rõ *đã thực hiện*, *chưa thực hiện* và *chưa xác minh*.

## 2. Quy trình bắt buộc cho mọi thay đổi

**Trước khi viết hoặc sửa bất kỳ dòng code nào, phải tìm và đọc skill phù hợp với nhiệm vụ.** Kiểm tra danh mục skill sẵn có của môi trường/IDE, đọc đầy đủ `SKILL.md` và các tài liệu tham chiếu bắt buộc có liên quan; áp dụng hướng dẫn vào cách làm và kiểm chứng. Nếu có nhiều skill phù hợp, ưu tiên skill chuyên biệt nhất rồi phối hợp khi cần. Không viện dẫn skill chưa thực sự đọc, không cài hoặc tạo skill chỉ để đủ thủ tục. Nếu không có skill liên quan, ghi nhận ngắn gọn và chuyển sang tài liệu chính thức, test cùng code hiện hữu. Khi nhiệm vụ đổi phạm vi hoặc đổi công nghệ, kiểm tra lại skill trước khi tiếp tục.

1. **Hiểu:** xác định yêu cầu, hành vi hiện tại, hành vi mong đợi, các module chịu ảnh hưởng và rủi ro.
2. **Đọc:** tìm hàm, service, test, schema và cấu hình có sẵn; ưu tiên tái sử dụng thay vì tạo mới.
3. **Thiết kế tối thiểu:** chọn phương án rõ ràng nhất đáp ứng yêu cầu; xác định dữ liệu, lỗi, giao dịch và điều kiện biên.
4. **Sửa đúng chỗ:** thay đổi ít file nhất có thể nhưng đủ để giải quyết vấn đề ở tầng sở hữu logic.
5. **Kiểm chứng:** chạy test liên quan, kiểm tra regression, type/lint khi phù hợp và xác minh hành vi thật.
6. **Dọn dẹp:** loại bỏ code cũ đã được thay thế, đường dẫn không còn dùng, import thừa, file tạm, log debug và tài liệu sai lệch.
7. **Báo cáo gọn:** nêu đã thay đổi gì, vì sao, đã kiểm tra bằng lệnh nào, kết quả gì và còn hạn chế nào.

Không bỏ qua bước kiểm chứng và dọn dẹp để lấy tốc độ. Không mở rộng phạm vi một cách ngẫu nhiên khi sửa một lỗi nhỏ.

### Bảng tra cứu Agent Skills dự án theo giai đoạn công việc

Trước khi thực hiện từng giai đoạn, Agent phải chủ động tra cứu và đọc file `SKILL.md` tương ứng trong `.agents/skills/` (hoặc skill môi trường):

| Giai đoạn công việc | Tình huống / Nhiệm vụ | Skill chỉ định | Đường dẫn SKILL.md |
| :--- | :--- | :--- | :--- |
| **Thiết lập context** | Thiết lập quy ước issue tracker, nhãn domain cho skills | `setup-matt-pocock-skills` | `.agents/skills/setup-matt-pocock-skills/SKILL.md` |
| **Lập kế hoạch** | Chia nhỏ spec/yêu cầu thành các tickets có dependency rõ ràng | `to-tickets` | `.agents/skills/to-tickets/SKILL.md` |
| **Thiết kế kiến trúc** | Thiết kế interface, deep module, ranh giới domain sạch | `codebase-design` | `.agents/skills/codebase-design/SKILL.md` |
| **Triển khai code** | Viết code thực thi theo ticket hoặc spec đã duyệt | `implement` | `.agents/skills/implement/SKILL.md` |
| **Lập trình kiểm thử** | Phát triển tính năng mới hoặc bugfix theo quy trình test-first (TDD) | `tdd` | `.agents/skills/tdd/SKILL.md` |
| **Debug / Điều tra lỗi** | Phân tích root cause lỗi phức tạp, tái hiện lỗi, fix tận gốc | `diagnosing-bugs` | `.agents/skills/diagnosing-bugs/SKILL.md` |
| **LangGraph / Workflow** | Xây dựng node, edge, state graph, checkpointer, human-in-the-loop | `langgraph-fundamentals` | `.agents/skills/langgraph-fundamentals/SKILL.md` |
| **PostgreSQL / Database** | Thiết kế schema, index, query SQL tối ưu, migration an toàn | `postgres-best-practices` | `.agents/skills/postgres-best-practices/SKILL.md` |
| **Giao diện / UX** | Thiết kế định hướng thị giác, layout, typography không generic | `frontend-design` | `.agents/skills/frontend-design/SKILL.md` |
| **React / Frontend** | Tối ưu hiệu năng React, tránh re-render thừa, waterfall fetching | `vercel-react-best-practices` | `.agents/skills/vercel-react-best-practices/SKILL.md` |
| **Kiểm thử Web / UI** | Chạy kiểm thử tương tác frontend, chụp màn hình, logs Playwright | `webapp-testing` | `.agents/skills/webapp-testing/SKILL.md` |
| **Review code định kỳ** | Review đối chiếu hai trục Standards & Spec trước khi merge | `code-review` | `.agents/skills/code-review/SKILL.md` |
| **Review an ninh diff** | Đánh giá diff/PR theo góc độ bảo mật, blast radius, test coverage | `differential-review` | `.agents/skills/differential-review/SKILL.md` |
| **Nghiệm thu hoàn tất** | Bắt buộc chạy lệnh kiểm chứng thật trước khi báo cáo hoàn thành | `verification-before-completion` | Sẵn có trong môi trường / IDE global |

## 3. Clean code — gọn, rõ, nhất quán

- **Ưu tiên code dễ đọc hơn code “thông minh”.** Đặt tên theo ý nghĩa nghiệp vụ; tránh chữ viết tắt khó hiểu, magic numbers và hàm đa nhiệm.
- Một hàm nên làm một việc; giữ side effects tường minh. Dùng guard clauses để tránh lồng `if` sâu.
- Chỉ trừu tượng hóa khi có nhu cầu thật. Không tạo interface, class, base class, generic helper hoặc factory chỉ để “trông enterprise”.
- Không copy/paste logic nghiệp vụ. Dồn về một service hoặc policy engine có trách nhiệm rõ; tránh abstraction chung chung không có chủ sở hữu.
- Hàm và module nên ngắn, nhưng **không chia vụn code** chỉ để đạt giới hạn dòng. Tham khảo ngưỡng của kế hoạch (hàm ~60 dòng, module ~400 dòng); nếu vượt, xem xét tách theo trách nhiệm.
- Ưu tiên type hints Python, Pydantic ở ranh giới dữ liệu, TypeScript strict ở frontend. Tránh `Any`, `dict` vô cấu trúc khi đã biết schema.
- Exception phải có ý nghĩa và ngữ cảnh; không `except Exception: pass`, `catch {}`, hoặc trả kết quả thành công khi thao tác thất bại.
- Không nuốt lỗi để giao diện “xanh”. Không tự động sửa dữ liệu sai bằng fallback im lặng.
- Comment giải thích *vì sao* khi logic không hiển nhiên; không mô tả lại từng dòng code. Docstring cần thiết cho public API và tool.
- Không thêm icon/emoji, ASCII art hoặc banner phân cách kiểu `======`, `********`, `########` vào console output, log, code và tài liệu nếu không thực sự có ý nghĩa. Output rõ và có cấu trúc, không trang trí.

## 4. Đặt tên file và bảo vệ cấu trúc repository

- **File dài hoặc ôm nhiều trách nhiệm phải được tách thành các module nhỏ hơn theo chức năng.** Giữ public interface rõ ràng, tách logic nghiệp vụ, I/O, schemas, adapters và orchestration khi chúng là các trách nhiệm khác nhau. Không tách cơ học theo số dòng, không tạo một file cho mỗi hàm, không làm tăng tầng abstraction vô ích. Nếu file dài nhưng có một trách nhiệm rõ và vẫn dễ đọc, có thể giữ nguyên với lý do cụ thể.
- **Folder có quá nhiều file hoặc nhiều nhóm chức năng phải được chia thành các thư mục con theo domain/feature hoặc trách nhiệm.** Ví dụ: `domain/orders/`, `domain/returns/`, `domain/refunds/` thay vì dồn hàng chục file không liên quan trong `domain/`. Chỉ tạo cấp thư mục khi cải thiện khả năng tìm kiếm và bảo trì; không lồng nhiều tầng rỗng hoặc chia theo tên phiên bản/lần sửa.
- Khi tách module/folder, **di chuyển code hiện hữu**, cập nhật toàn bộ imports, exports, test paths và tài liệu; kiểm tra tránh import vòng; giữ một implementation làm nguồn sự thật. Xóa file cũ không còn dùng sau khi regression PASS. Không để wrapper chuyển tiếp, alias tương thích hoặc folder cũ vô thời hạn nếu không có người dùng thực sự phụ thuộc.
- Trước khi tạo file mới, **kiểm tra file/folder có sẵn và sơ đồ thư mục**. Nên gộp phần liên quan chặt chẽ và tách phần khác trách nhiệm, không chia chỉ vì muốn đẹp cây thư mục.

- Tên file và thư mục phải biểu thị **trách nhiệm ổn định**, theo quy ước của ngôn ngữ: Python `snake_case.py`, TypeScript `camelCase.ts` hoặc tên đang được repo sử dụng nhất quán, React component `PascalCase.tsx`.
- **Cấm đặt tên theo lịch sử sửa chữa hoặc phiên bản tạm:** `fix.py`, `fix_new.py`, `refund_v2.py`, `refund_final.py`, `agent_new.py`, `service_old.py`, `temp_test.py`, `copy_of_*.py`, `backup_*.ts`.
- Sửa trực tiếp module đúng trách nhiệm. Nếu cần thay module, chuyển phần còn dùng sang module mới có tên nghiệp vụ, cập nhật import/test rồi **xóa module cũ** khi đã xác minh.
- Ngoại lệ hợp lệ: file migration được đánh số theo công cụ, fixture được gắn mã case, artefact release/evaluation có ID hoặc timestamp theo chuẩn của hệ thống.
- Không tạo nhiều file trung gian để thử từng cách fix. Thử nhanh trong terminal hoặc thư mục tạm ngoài repo; chỉ giữ lại thứ có giá trị lâu dài.
- Không tạo `utils.py`, `helpers.py`, `common.py` khổng lồ chứa logic không liên quan. Đặt logic vào package sở hữu nghiệp vụ.
- Trước khi tạo thư mục hoặc file mới, trả lời được: **nó chịu trách nhiệm gì, vì sao file hiện tại không phù hợp, ai sử dụng và test ở đâu?**
- Sau khi thay đổi cấu trúc: cập nhật import, tài liệu và test; không để nhiều đường thực thi cũ/mới cùng tồn tại vô thời hạn.
- Không sửa hàng loạt file không liên quan, không format lại toàn repo chỉ vì thay đổi nhỏ.

## 5. Ranh giới kiến trúc của `shop-support-agent`

- Tuân thủ cấu trúc và ADR trong kế hoạch: `core/`, `domain/`, `infra/`, `rag/`, `agent/`, `api/`, `evals/`, `frontend/`.
- **`domain/` là nguồn sự thật cho luật nghiệp vụ**; không phụ thuộc FastAPI, LangGraph, SDK LLM hoặc frontend. Tool chỉ xác thực input, gọi service được phân quyền và định dạng output.
- Mọi service nghiệp vụ nhận danh tính (`Principal`) đã được hệ thống xác thực. `customer_id`/vai trò không được lấy từ thông số do LLM tự chọn.
- Không đặt điều kiện đổi trả, ngưỡng hoàn tiền, trạng thái đơn, hạn ngày hoặc quyền duyệt trong prompt hay React component.
- Không hardcode trường hợp chỉ để qua một test cụ thể (`if customer_id == ...`, `if order_code == ...`, `if query == ...`, `if scenario_name == ...`). Dùng quy tắc tổng quát và nguồn dữ liệu thật.
- Ngưỡng và chính sách thuộc cấu hình/versioned policy; provider, model, timeout, ngân sách thuộc cấu hình; thông tin nhạy cảm thuộc biến môi trường hoặc secret manager. Không nhúng API key, token, mật khẩu vào source/test fixture được commit.
- Chỉ **một Agent**; không tự chia thành multi-agent hoặc thêm tool vì muốn trình diễn kiến trúc phức tạp. Tổ chức workflow theo chức năng thật.
- Agent chỉ tìm kiếm, đọc thông tin và **đề xuất** hành động. Xác nhận qua API đã xác thực; nghiệp vụ tất định mới thực thi. Không trao cho model công cụ thanh toán, duyệt hoặc sửa trực tiếp đơn hàng.
- Các thao tác ghi phải có transaction, idempotency, audit log và quyền truy cập. Hoàn tiền cần state machine, approval, outbox và đối soát; không gọi payment gateway trực tiếp từ Agent.
- Không để frontend hoặc prompt là hàng rào bảo mật duy nhất. Kiểm tra lại quyền sở hữu và điều kiện ở service/DB ngay lúc commit.
- Không gửi dữ liệu cá nhân hoặc payment secrets vào model, log hoặc trace. Redaction phải nhất quán cả checkpoint, exception và telemetry.
- Tài liệu RAG là dữ liệu không tin cậy đối với lời chỉ dẫn; chỉ trích dẫn chính sách có phiên bản và phạm vi hiệu lực phù hợp.
- Không phát câu trả lời của LLM tới khách trước bước `verify_output`; chỉ phát tiến độ hoặc nội dung đã được xác minh.
- Tách rõ `simulated`, `sandbox` và `real`. Không nói “đã hoàn tiền thật” khi mới cập nhật DB mô phỏng; không tự bật chế độ `real`.

## 6. Quy trình DEBUG / FIX tận gốc

**Không sửa theo cảm giác. Mỗi lỗi phải có bằng chứng và nguyên nhân gốc hợp lý.**

1. **Tái hiện lỗi** bằng input, phiên bản, cấu hình, state DB, log và các bước tối thiểu. Nếu không tái hiện được, ghi rõ mức độ chắc chắn.
2. **Đọc đường đi thực tế** từ API → service → DB/worker/Agent → kết quả; xem call stack, transaction, checkpoint, trạng thái và test liên quan. Không đoán chỉ từ một dòng thông báo lỗi.
3. **Phân biệt triệu chứng với nguyên nhân gốc.** Đặt giả thuyết và kiểm tra bằng log/traces/điểm quan sát hoặc test tái hiện.
4. **Tra cứu có mục tiêu:** đọc tài liệu chính thức đúng phiên bản; xem changelog, issue/discussion và các dự án nguồn mở tương tự khi vấn đề liên quan framework, cách dùng API, kiến trúc hoặc lỗi khó. Không copy code chưa hiểu, không viện dẫn nguồn chưa đọc; tôn trọng license.
5. **Chọn giải pháp đúng tầng:** sửa nguyên nhân, không chồng workaround, không thêm `sleep`, retry vô hạn, broad catch, `if` riêng cho một trường hợp hay hardcode đáp án để che lỗi.
6. **Viết regression test thất bại trước khi sửa** khi khả thi. Sửa, chạy lại đúng ca lỗi rồi chạy các ca kề cận và bộ test cần thiết.
7. **Dọn hậu fix:** xóa code/branch logic cũ không còn dùng, debug prints, feature flag tạm, file `*_fix`, import rác và những giải pháp thử nghiệm thất bại. Giữ nguyên migration, dữ liệu và bằng chứng cần thiết cho khả năng audit.
8. **Kết luận minh bạch:** nguyên nhân gốc, cách sửa, các test PASS/FAIL/SKIP, rủi ro còn lại. Nếu chỉ là workaround, phải nói rõ và không gọi là giải pháp dứt điểm.

**Tuyệt đối không:** sửa đi sửa lại một file bằng cách đoán; đổi model/prompt liên tục mà không đo; tắt validation; bỏ assert; nới điều kiện phê duyệt; viết test khớp riêng implementation lỗi; sửa ground truth để kết quả đẹp hơn.

## 7. Testing và evaluation

- Kiểm thử theo mức: unit (luật thuần), integration (Postgres/API/worker), contract (tool/provider), E2E (UI), security/concurrency/resilience và Agent evaluation.
- Ưu tiên **test trước** cho luật nghiệp vụ, quyền truy cập, state machine, idempotency và thay đổi tool. Với lỗi hồi quy, thêm test nhỏ nhất chứng minh đúng nguyên nhân.
- Dùng clock/seed/fixture tiêm được, môi trường reset và dữ liệu tái lập. Không phụ thuộc thời gian hiện tại, thứ tự chạy hoặc dữ liệu lần trước.
- **Ground truth và bộ chấm độc lập với Agent**; không để model đọc expected DB state; không thay oracle để hợp thức hóa kết quả.
- Không dùng mock để tuyên bố integration/E2E đã PASS. Mock tests và real integration tests phải ghi nhãn rõ.
- Mọi thay đổi prompt, model, tool schema, RAG retrieval và workflow cần chạy các ca eval liên quan; lưu chênh lệch so với baseline đã có.
- Không đưa số liệu benchmark tưởng tượng vào README. Ghi rõ bộ dữ liệu, model ID, cấu hình, số lần chạy, ngày chạy, failed/skipped và chi phí khi có.
- Không bỏ qua tests bị SKIP/FAIL. Nếu giới hạn môi trường hoặc không có API key, phân biệt `not run` với `passed`.
- Với hành động nhạy cảm, phải có tests cho phân quyền ngang, xác nhận sai/chậm, hai request đồng thời, retry/resume, double-refund, crash giữa transaction và provider callback lặp.

## 8. Console output, log, artefact và dọn rác

- **Output ngắn, có ích và nhất quán**: sự kiện, trạng thái, định danh liên quan, lỗi có nguyên nhân. Không in chuỗi `================`, banner dài, log mọi token LLM hoặc toàn bộ JSON nhạy cảm.
- Dùng structured logging (`level`, `event`, `request_id`/`trace_id`, `error_code`), với mức log điều khiển bằng cấu hình. Không để `print()` debug rải trong code production.
- Trong lúc điều tra, log chi tiết có thể bật tạm thời; **tắt và dọn sạch sau khi sửa**. Không xóa log audit, trace nghiệm thu hoặc evidence cần để truy vết sự cố.
- Đầu ra thử nghiệm, screenshot tạm, trace rác, cache, build, coverage, file tải và log debug không thuộc source: đặt ở thư mục output đã được `.gitignore` hoặc ở thư mục tạm; không commit.
- Chỉ giữ trong repo các fixtures, benchmark baseline, report và evidence **có giá trị tái lập** theo cấu trúc được duyệt. Không để `output1`, `result_final2`, `test-new`, `logs-copy` rải khắp project.
- Khi hoàn thành một task, kiểm tra `git status`, danh sách file mới, folder trống, artefact tạm, dead code, secret và import thừa. Không xóa file người dùng hay artefact nghiệm thu nếu chưa chắc nguồn gốc.

## 9. Phụ thuộc, tài liệu và Git

- Trước khi thêm thư viện, kiểm tra dependency hiện có có giải quyết được không; đọc tài liệu chính thức cho API của version đang khóa. Nếu thêm dependency, nêu lợi ích, chi phí và cập nhật lockfile.
- Không tăng số service chỉ để làm theo tutorial. Ưu tiên stack đã chốt trong kế hoạch và giải pháp đủ đơn giản cho Windows 16GB RAM.
- Không viết lại một thư viện đã giải quyết tốt bài toán, nhưng cũng không phụ thuộc thư viện lớn cho thao tác nhỏ.
- README nói **cách chạy thật**; không đưa hướng dẫn hoặc screenshot chưa kiểm chứng. Tài liệu mô tả kiến trúc và quyết định, không ghi nhật ký sửa vặt dài dòng.
- Thay đổi hành vi/kiến trúc quan trọng phải cập nhật ADR hoặc tài liệu tương ứng; không tạo nhiều file `PLAN_V2.md`, `REPORT_FINAL.md`, `NOTES_FIX.md`.
- Commit theo nhóm thay đổi có ý nghĩa; không commit secret, `.env`, database dump, file tạm hoặc artifacts không cần thiết.
- Không `git reset --hard`, force-push, xoá dữ liệu hoặc migration nguy hiểm nếu chưa kiểm tra hậu quả và có quyền phù hợp.

## 10. Khuôn báo cáo sau mỗi task

Trả lời ngắn, bằng tiếng Việt, không banner trang trí hoặc danh sách các việc tưởng tượng:

- **Đã làm:** tính năng/lỗi và những file chính thay đổi.
- **Lý do:** nguyên nhân gốc hoặc quyết định thiết kế quan trọng.
- **Kiểm chứng:** lệnh đã chạy, số PASS/FAIL/SKIP hoặc hành vi thực tế quan sát được.
- **Còn lại:** giới hạn, rủi ro và bước tiếp theo nếu có.

Nếu chưa chạy được test vì môi trường, API key, service hoặc quyền truy cập, nói rõ **chưa kiểm chứng**. Không dùng các câu “hoàn thành 100%”, “production ready”, “đã tối ưu” khi không có bằng chứng.

## 11. Checklist tự kiểm trước khi kết thúc

- [ ] Đã tìm và đọc skill có liên quan trước khi code; nếu không có skill phù hợp thì đã dựa trên tài liệu chính thức và code/test hiện hữu.
- [ ] Logic được đặt đúng module, đúng tầng; không hardcode cho test case riêng.
- [ ] File quá dài hoặc nhiều trách nhiệm đã được phân tách hợp lý; folder đông file đã nhóm thành các thư mục con theo chức năng, không chia vụn hoặc lồng tầng thừa.
- [ ] Tên file phản ánh trách nhiệm; không có file `fix`, `v2`, `final`, `old`, `temp` tùy tiện.
- [ ] Không còn code thử nghiệm, implementation cũ bị thay thế, import thừa hoặc debug prints.
- [ ] Không có banner `======`, output rác, log nhạy cảm hoặc artefact tạm được commit.
- [ ] Đã kiểm tra quyền truy cập, transaction, idempotency và audit với mọi hành động ghi.
- [ ] Test liên quan thực sự chạy; lỗi có regression test; không sửa yếu oracle/evaluator.
- [ ] Có báo cáo rõ PASS/FAIL/SKIP và những gì chưa xác minh.
- [ ] README/ADR/config/lockfile được cập nhật nếu thay đổi hành vi hoặc phụ thuộc.
- [ ] Không phá hỏng dữ liệu, evidence, lịch sử migration hoặc thay đổi người khác không liên quan.

**Nguyên tắc cuối:** _Sửa đúng nguyên nhân. Giữ một implementation rõ ràng. Dọn hết phần thừa. Chỉ tuyên bố thành công khi có kiểm chứng._
