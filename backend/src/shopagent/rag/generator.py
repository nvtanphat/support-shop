"""Policy document and clause generator from rules.yaml."""

from __future__ import annotations

from typing import Any

import jinja2

from shopagent.core.config import get_rules_config

_CLAUSE_TEMPLATES: list[dict[str, Any]] = [
    {
        "clause_id": "POL-RETURN-01",
        "topic": "return",
        "category_scope": ["all"],
        "template": (
            "Chính sách đổi trả hàng do lỗi cửa hàng hoặc nhà sản xuất. "
            "Thời hạn yêu cầu: trong vòng {{ r.return.windows_days.defect_like }} ngày kể từ ngày giao hàng thành công. "
            "Các lý do áp dụng: lỗi sản phẩm, hư hỏng trong quá trình vận chuyển, giao sai món, thiếu món, không đúng mô tả. "
            "Phí vận chuyển: Cửa hàng chịu toàn bộ chi phí vận chuyển chiều về. "
            "Bằng chứng yêu cầu: Bắt buộc cung cấp tối thiểu {{ r.return.evidence.min_photos }} ảnh rõ nét về tình trạng hàng hóa. "
            "Trường hợp thiếu hàng bắt buộc phải có video mở hộp (unboxing)."
        ),
    },
    {
        "clause_id": "POL-RETURN-02",
        "topic": "return",
        "category_scope": ["all"],
        "template": (
            "Chính sách đổi trả do khách hàng đổi ý không còn nhu cầu (Change of mind). "
            "Thời hạn yêu cầu: trong vòng {{ r.return.windows_days.change_of_mind }} ngày kể từ khi nhận hàng. "
            "Điều kiện hàng hóa: Chưa qua sử dụng, còn nguyên tem mác, hộp đựng và phụ kiện quà tặng kèm theo. "
            "Phí vận chuyển: Khách hàng chịu phí vận chuyển chiều về là {{ r.return.return_shipping.customer_fee_vnd }} đ, "
            "khoản phí này sẽ được khấu trừ trực tiếp vào tổng số tiền hoàn."
        ),
    },
    {
        "clause_id": "POL-RETURN-03",
        "topic": "return",
        "category_scope": ["excluded"],
        "template": (
            "Danh mục hàng hóa loại trừ không áp dụng chính sách đổi trả khi đổi ý. "
            "Các sản phẩm thuộc nhóm sau đây không được trả hàng vì lý do đổi ý: "
            "hàng xả kho giảm giá sâu (final sale), đồ lót và đồ bơi vì lý do vệ sinh (hygiene), "
            "mỹ phẩm đã bóc niêm phong hoặc mở nắp (sealed cosmetic), sản phẩm in ấn hoặc khắc tên cá nhân hóa theo yêu cầu (personalized), "
            "và thẻ quà tặng (gift cards)."
        ),
    },
    {
        "clause_id": "POL-RETURN-04",
        "topic": "return",
        "category_scope": ["all"],
        "template": (
            "Quy định về thời hạn gửi hàng trả về kho cửa hàng. "
            "Sau khi yêu cầu đổi trả được phê duyệt và chấp thuận, khách hàng có thời hạn tối đa "
            "{{ r.return.ship_back_deadline_days }} ngày để giao kiện hàng cho bưu cục vận chuyển. "
            "Hạn chót tính theo mốc {{ r.return.deadline_rule }}. "
            "Nếu quá thời hạn trên mà hàng chưa được gửi, yêu cầu đổi trả sẽ tự động hết hiệu lực."
        ),
    },
    {
        "clause_id": "POL-REFUND-01",
        "topic": "refund",
        "category_scope": ["all"],
        "template": (
            "Thời gian và tiến độ hoàn tiền theo phương thức thanh toán gốc của đơn hàng. "
            "Sau khi khoản hoàn được phê duyệt và giải ngân: "
            "Ví điện tử nhận tiền trong vòng {{ r.refund.sla_working_days.ewallet[0] }} đến {{ r.refund.sla_working_days.ewallet[1] }} ngày làm việc. "
            "Chuyển khoản tài khoản ngân hàng nhận tiền trong vòng {{ r.refund.sla_working_days.bank_transfer[0] }} đến {{ r.refund.sla_working_days.bank_transfer[1] }} ngày làm việc. "
            "Thẻ tín dụng hoặc ghi nợ quốc tế nhận tiền trong vòng {{ r.refund.sla_working_days.card[0] }} đến {{ r.refund.sla_working_days.card[1] }} ngày làm việc tùy thuộc ngân hàng phát hành thẻ."
        ),
    },
    {
        "clause_id": "POL-REFUND-02",
        "topic": "refund",
        "category_scope": ["all"],
        "template": (
            "Hạn mức duyệt và thẩm quyền giải ngân hoàn tiền. "
            "Khoản hoàn tiền từ {{ r.refund.auto_approve_max_vnd }} đ trở xuống không có cờ rủi ro: Hệ thống tự động phê duyệt ngay. "
            "Khoản hoàn tiền trên {{ r.refund.auto_approve_max_vnd }} đ đến {{ r.refund.agent_approve_max_vnd }} đ: Nhân viên chăm sóc khách hàng (agent) xem xét phê duyệt. "
            "Khoản hoàn tiền trên {{ r.refund.agent_approve_max_vnd }} đ hoặc phát hiện cờ rủi ro: Bắt buộc Trưởng nhóm (supervisor) xem xét và phê duyệt."
        ),
    },
    {
        "clause_id": "POL-CANCEL-01",
        "topic": "cancel",
        "category_scope": ["all"],
        "template": (
            "Quy định hủy đơn hàng và các trạng thái đơn áp dụng. "
            "Tự phục vụ hủy đơn: Đơn hàng ở trạng thái chờ thanh toán ({{ r.cancel.self_service_statuses[0] }}) hoặc "
            "đã xác nhận ({{ r.cancel.self_service_statuses[1] }}) được hủy tự động ngay sau khi khách bấm nút xác nhận. "
            "Cần duyệt hủy: Đơn hàng ở trạng thái đang đóng gói ({{ r.cancel.needs_approval_statuses[0] }}) cần nhân viên kho kiểm tra và duyệt yêu cầu hủy. "
            "Không thể hủy: Đơn hàng đã xuất kho chuyển giao cho đơn vị vận chuyển (shipped, out_for_delivery, delivered) "
            "không thể hủy trực tiếp. Khách hàng vui lòng từ chối nhận hàng khi shipper giao hoặc làm thủ tục trả hàng sau khi nhận."
        ),
    },
    {
        "clause_id": "POL-EXCHANGE-01",
        "topic": "exchange",
        "category_scope": ["all"],
        "template": (
            "Chính sách đổi hàng áp dụng cho sản phẩm thời trang và tiêu dùng. "
            "Quy tắc đổi hàng: Cửa hàng chỉ hỗ trợ đổi cùng sản phẩm nhưng khác phân loại như kích thước (size) hoặc màu sắc. "
            "Yêu cầu về giá: Sản phẩm đổi phải có cùng mức giá với phân loại ban đầu. "
            "Giới hạn: Mỗi món hàng chỉ được hỗ trợ đổi tối đa {{ r.exchange.max_times_per_item }} lần duy nhất và phân loại mới phải còn tồn kho khả dụng."
        ),
    },
    {
        "clause_id": "POL-GENERAL-01",
        "topic": "general",
        "category_scope": ["all"],
        "template": (
            "Quy định chung về dịch vụ chăm sóc khách hàng và đồng hồ chính sách cửa hàng ShopLab. "
            "Phiên bản chính sách hiện hành: {{ r.version }}. "
            "Cửa hàng áp dụng múi giờ chuẩn {{ r.timezone }}. "
            "Các đề xuất hành động hủy đơn hoặc trả hàng có thời hạn hiệu lực {{ r.pending_action_ttl_minutes }} phút kể từ khi tạo. "
            "Mọi thắc mắc ngoài phạm vi tự phục vụ, khách hàng luôn có quyền yêu cầu kết nối với nhân viên hỗ trợ trực tiếp bất cứ lúc nào."
        ),
    },
]


def generate_policy_clauses(rules: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Render all policy clauses dynamically using rules config."""
    if rules is None:
        rules = get_rules_config()

    jinja_env = jinja2.Environment()
    clauses = []

    for item in _CLAUSE_TEMPLATES:
        template = jinja_env.from_string(item["template"])
        rendered_text = template.render(r=rules)
        clauses.append({
            "clause_id": item["clause_id"],
            "topic": item["topic"],
            "category_scope": item["category_scope"],
            "version": rules.get("version", "2026-11-01"),
            "effective_from": rules.get("effective_from"),
            "effective_to": rules.get("effective_to"),
            "text": rendered_text,
        })

    return clauses
