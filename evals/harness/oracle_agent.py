"""Deterministic Oracle Agent achieving 100% on standard scenarios without LLM."""

from __future__ import annotations

import re
import uuid
from typing import Any

from shopagent.core.principal import Principal
from shopagent.domain.models.enums import (
    ReturnReason,
)
from shopagent.domain.policies.rules import PolicyRules
from shopagent.domain.services.actions import ActionService
from shopagent.domain.services.cancellations import CancellationService
from shopagent.domain.services.orders import OrderService
from shopagent.domain.services.returns import ReturnService
from shopagent.domain.services.tickets import TicketService
from shopagent.infra.db.tables import OrderItemModel, OrderModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evals.harness.models import Scenario


class OracleAgent:
    """Deterministic agent following exact domain policies and business procedures."""

    def __init__(
        self,
        session: AsyncSession,
        principal: Principal,
        scenario: Scenario | None = None,
    ) -> None:
        self.session = session
        self.principal = principal
        self.scenario = scenario
        self.policy = PolicyRules()
        self.order_service = OrderService(session)
        self.return_service = ReturnService(session)
        self.cancellation_service = CancellationService(session)
        self.action_service = ActionService(session)
        self.ticket_service = TicketService(session)

    async def step(
        self,
        conversation_id: str,
        user_message: str,
        dialogue_history: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        """Process user message and return assistant reply, tool calls, and proposed action."""
        msg_lower = user_message.lower()
        tool_calls: list[dict[str, Any]] = []

        # Find order code in user message or history
        order_code = None
        match = re.search(r"\b(SL-\w+)\b", user_message, re.IGNORECASE)
        if match:
            order_code = match.group(1).upper()
        else:
            for turn in reversed(dialogue_history):
                m = re.search(r"\b(SL-\w+)\b", turn.get("content", ""), re.IGNORECASE)
                if m:
                    order_code = m.group(1).upper()
                    break

        # 1. Escalation / Human handoff
        if any(w in msg_lower for w in ("gặp nhân viên", "chuyển người", "tổng đài", "tranh chấp", "bức xúc")):
            ticket = await self.ticket_service.create_ticket(
                principal=self.principal,
                conversation_id=uuid.UUID(conversation_id),
                reason_code="customer_request",
                agent_summary=user_message,
                priority="high",
            )
            tool_calls.append({"tool": "escalate_to_human", "args": {"reason": "customer_request"}})
            return (
                f"Em đã tạo phiếu hỗ trợ #{ticket.code} chuyển đến chuyên viên chăm sóc khách hàng. "
                "Nhân viên sẽ liên hệ lại với quý khách trong vòng 30 phút.",
                tool_calls,
                None,
            )

        # 2. Return & Refund Request
        if any(w in msg_lower for w in ("trả", "đổi trả", "hoàn tiền", "đổi ý", "lỗi", "hỏng")):
            if not order_code and self.scenario and self.scenario.fixtures.get("orders"):
                order_code = self.scenario.fixtures["orders"][0]["code"]

            if order_code:
                # Find order
                stmt = select(OrderModel).where(OrderModel.code == order_code)
                res = await self.session.execute(stmt)
                order_model = res.scalar_one_or_none()

                if order_model:
                    # Check items
                    items_stmt = select(OrderItemModel).where(OrderItemModel.order_id == order_model.id)
                    items_res = await self.session.execute(items_stmt)
                    items = items_res.scalars().all()

                    # Reason detection
                    if any(w in msg_lower for w in ("đổi ý", "không thích", "không vừa", "mặc không ưng", "xả kho", "đồ lót")):
                        reason = ReturnReason.CHANGE_OF_MIND
                    else:
                        reason = ReturnReason.DEFECTIVE

                    item_ids = [str(items[0].id)] if items else []
                    if self.scenario and any(w in msg_lower for w in ("vay", "váy")) and len(items) > 1:
                        item_ids = [str(items[1].id)]

                    tool_calls.append({
                        "tool": "check_return_eligibility",
                        "args": {"order_code": order_code, "reason": reason.value},
                    })

                    try:
                        elig = await self.return_service.check_eligibility_for_principal(
                            principal=self.principal,
                            order_code=order_code,
                            item_ids=item_ids,
                            reason_code=reason.value,
                        )
                        if not elig["eligible"]:
                            return (
                                f"Đơn hàng {order_code} không đủ điều kiện đổi trả theo [{elig['clause_id']}]: {elig['message']}",
                                tool_calls,
                                None,
                            )
                    except Exception as err:
                        return (
                            f"Không thể kiểm tra đổi trả đơn {order_code}: {err}",
                            tool_calls,
                            None,
                        )

                    # Propose return
                    if item_ids:
                        items_payload = [{"item_id": i_id, "qty": 1} for i_id in item_ids]
                        prop_res = await self.return_service.propose_return(
                            principal=self.principal,
                            conversation_id=uuid.UUID(conversation_id),
                            order_code=order_code,
                            items=items_payload,
                            reason_code=reason.value,
                            resolution="refund",
                        )
                        tool_calls.append({
                            "tool": "propose_return",
                            "args": {"order_code": order_code, "items": items_payload},
                        })
                        p_dict = {
                            "id": prop_res["action_id"],
                            "type": prop_res["type"],
                            "preview_hash": prop_res["preview_hash"],
                            "preview": prop_res["preview"],
                        }
                        clause = "[POL-RETURN-02]" if reason == ReturnReason.CHANGE_OF_MIND else "[POL-RETURN-01]"
                        refund_val = prop_res["preview"].get("estimated_refund", 0)
                        return (
                            f"Yêu cầu đổi trả đơn hàng {order_code} đủ điều kiện theo chính sách {clause}. "
                            f"Ước tính số tiền hoàn trả là {refund_val:,} đ. "
                            "Em đã tạo biểu mẫu đề xuất đổi trả bên dưới, quý khách vui lòng kiểm tra và bấm 'Xác nhận' để gửi yêu cầu.",
                            tool_calls,
                            p_dict,
                        )

        # 3. Cancellation Request
        if order_code and any(w in msg_lower for w in ("hủy", "hủy đơn", "cancel")):
            stmt = select(OrderModel).where(OrderModel.code == order_code)
            res = await self.session.execute(stmt)
            order_model = res.scalar_one_or_none()
            if order_model:
                try:
                    prop_res = await self.cancellation_service.propose_cancellation(
                        principal=self.principal,
                        conversation_id=uuid.UUID(conversation_id),
                        order_code=order_code,
                        reason="Khách hàng yêu cầu hủy đơn",
                    )
                    tool_calls.append({"tool": "propose_cancel_order", "args": {"order_code": order_code}})
                    p_dict = {
                        "id": prop_res["action_id"],
                        "type": prop_res["type"],
                        "preview_hash": prop_res["preview_hash"],
                        "preview": prop_res["preview"],
                    }
                    return (
                        f"Em đã tạo đề xuất hủy đơn hàng {order_code}. "
                        "Quý khách vui lòng bấm nút 'Xác nhận hủy đơn' bên dưới để hoàn tất.",
                        tool_calls,
                        p_dict,
                    )
                except Exception:
                    return (
                        f"Đơn hàng {order_code} đang ở trạng thái {order_model.status}, không thể hủy trực tiếp.",
                        tool_calls,
                        None,
                    )

        # 3.5 Exchange inquiry
        if any(w in msg_lower for w in ("đổi size", "size", "đổi sang", "chật", "rộng")):
            return (
                "Theo quy định đổi trả [POL-RETURN-01], cửa hàng hỗ trợ đổi kích cỡ (size) sản phẩm tương đương trong vòng 15 ngày nếu sản phẩm còn hàng trong kho.",
                tool_calls,
                None,
            )

        # 4. Order Lookup / Tracking
        if order_code:
            try:
                order_dict = await self.order_service.get_order_for_principal(self.principal, order_code)
                tool_calls.append({"tool": "lookup_order", "args": {"order_code": order_code}})
                return (
                    f"Đơn hàng {order_dict['order_code']} hiện có trạng thái: {order_dict['status']}. "
                    f"Tổng giá trị đơn hàng là {order_dict['total']:,} đ.",
                    tool_calls,
                    None,
                )
            except Exception as err:
                return (
                    f"Không tìm thấy hoặc không có quyền truy cập đơn hàng {order_code}: {err}",
                    tool_calls,
                    None,
                )

        # 5. Policy Inquiries
        if any(w in msg_lower for w in ("bao nhiêu ngày", "hạn", "thời gian", "mấy ngày", "quy định", "chính sách", "phí", "bao lâu", "đổi size", "size", "chật")):
            if any(w in msg_lower for w in ("ví điện tử", "ewallet", "tiền hoàn")):
                return (
                    "Theo chính sách hoàn tiền [POL-REFUND-01], thời gian hoàn tiền về ví điện tử là 1-3 ngày làm việc.",
                    tool_calls,
                    None,
                )
            if any(w in msg_lower for w in ("đổi ý", "không thích", "không vừa", "phí")):
                return (
                    "Theo chính sách đổi trả [POL-RETURN-02], khách hàng đổi ý được trả hàng trong vòng 7 ngày "
                    "kể từ khi nhận hàng. Phí vận chuyển chiều về là 30.000 đ do khách hàng thanh toán.",
                    tool_calls,
                    None,
                )
            if any(w in msg_lower for w in ("đổi size", "size", "chật", "rộng")):
                return (
                    "Theo quy định đổi trả [POL-RETURN-01], cửa hàng hỗ trợ đổi kích cỡ (size) sản phẩm tương đương trong vòng 15 ngày nếu còn hàng.",
                    tool_calls,
                    None,
                )
            return (
                "Theo chính sách bảo hành và đổi trả lỗi [POL-RETURN-01], sản phẩm có lỗi từ nhà sản xuất "
                "hoặc hư hỏng do vận chuyển được đổi trả miễn phí trong vòng 15 ngày kể từ ngày nhận hàng.",
                tool_calls,
                None,
            )

        # Default fallback
        return (
            "Dạ em là trợ lý hỗ trợ khách hàng của ShopLab. Em có thể hỗ trợ quý khách tra cứu đơn hàng, "
            "hướng dẫn quy định đổi trả [POL-RETURN-01] hoặc tạo yêu cầu hủy đơn, hoàn tiền. Quý khách cần hỗ trợ gì ạ?",
            tool_calls,
            None,
        )
