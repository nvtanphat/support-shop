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
from shopagent.infra.db.tables import OrderItemModel, OrderModel, ProductModel, ProductVariantModel
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

    # Vietnamese words for the product keys used in scenario fixtures.
    _PRODUCT_WORDS: dict[str, tuple[str, ...]] = {
        "ao": ("áo",),
        "vay": ("váy",),
        "quan": ("quần",),
        "tat": ("tất",),
        "giay": ("giày",),
        "non": ("nón", "mũ"),
    }
    _ORDINALS: tuple[tuple[int, tuple[str, ...]], ...] = (
        (0, ("thứ nhất", "đầu tiên", "gần nhất", "mới nhất", "thứ 1")),
        (1, ("thứ hai", "thứ 2")),
        (2, ("thứ ba", "thứ 3")),
    )
    _CHANGE_OF_MIND_WORDS = ("đổi ý", "không thích", "không vừa", "mặc không ưng", "xả kho", "đồ lót")
    _DEFECT_WORDS = ("lỗi", "rách", "hỏng", "bung", "sờn", "dột", "méo")

    _POLICY_WORDS = ("bao nhiêu ngày", "hạn", "thời gian", "mấy ngày", "quy định", "chính sách", "phí", "bao lâu", "đổi size", "size", "chật")

    _pending_intent: str | None = None

    async def _recent_order_codes(self) -> list[str]:
        """Customer's orders, newest first - the same ordering the agent sees in its prompt."""
        if not self.principal.customer_id:
            return []
        stmt = (
            select(OrderModel.code)
            .where(OrderModel.customer_id == self.principal.customer_id)
            .order_by(OrderModel.placed_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _order_code_from(self, customer_text: str) -> str | None:
        matches = re.findall(r"\b(SL-\w+)\b", customer_text, re.IGNORECASE)
        if matches:
            return str(matches[-1]).upper()
        lowered = customer_text.lower()
        recent = await self._recent_order_codes()
        for index, words in self._ORDINALS:
            if any(w in lowered for w in words) and index < len(recent):
                return recent[index]
        return None

    async def _order_items(self, order_id: uuid.UUID) -> list[tuple[OrderItemModel, str]]:
        stmt = (
            select(OrderItemModel, ProductModel.name)
            .join(ProductVariantModel, ProductVariantModel.id == OrderItemModel.variant_id)
            .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
            .where(OrderItemModel.order_id == order_id)
        )
        return [(row[0], str(row[1])) for row in (await self.session.execute(stmt)).all()]

    def _pick_items(self, rows: list[tuple[OrderItemModel, str]], customer_text: str) -> list[OrderItemModel]:
        if len(rows) == 1:
            return [rows[0][0]]
        lowered = customer_text.lower()
        return [
            item
            for item, name in rows
            if any(w in lowered for w in self._PRODUCT_WORDS.get(name, (name,)))
        ]

    def _reason_from(self, customer_text: str) -> ReturnReason | None:
        lowered = customer_text.lower()
        if any(w in lowered for w in self._CHANGE_OF_MIND_WORDS):
            return ReturnReason.CHANGE_OF_MIND
        if any(w in lowered for w in self._DEFECT_WORDS):
            return ReturnReason.DEFECTIVE
        return None

    async def step(
        self,
        conversation_id: str,
        user_message: str,
        dialogue_history: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        """Process user message and return assistant reply, tool calls, and proposed action."""
        msg_lower = user_message.lower()
        tool_calls: list[dict[str, Any]] = []

        customer_text = " ".join(t["content"] for t in dialogue_history if t.get("role") == "customer")
        order_code = await self._order_code_from(customer_text)
        if order_code is None:
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
            tool_calls.append({"tool": "escalate_to_human", "args": {"reason_code": "customer_request", "summary": user_message}})
            return (
                f"Em đã tạo phiếu hỗ trợ #{ticket.code} chuyển đến chuyên viên chăm sóc khách hàng. "
                "Nhân viên sẽ liên hệ lại với quý khách trong vòng 30 phút.",
                tool_calls,
                None,
            )

        # 2. Return & Refund Request (slot filling: order, item, reason - never guessed)
        is_return_turn = any(w in msg_lower for w in ("trả", "đổi trả", "hoàn tiền", "đổi ý", "lỗi", "hỏng"))
        is_policy_question = any(w in msg_lower for w in self._POLICY_WORDS) and not order_code
        if (is_return_turn and not is_policy_question) or self._pending_intent == "return":
            self._pending_intent = "return"
            if not order_code:
                return (
                    "Quý khách vui lòng cho em xin mã đơn hàng cần đổi trả, hoặc cho biết đơn thứ mấy "
                    "trong danh sách đơn gần đây ạ?",
                    tool_calls,
                    None,
                )

            stmt = select(OrderModel).where(OrderModel.code == order_code)
            order_model = (await self.session.execute(stmt)).scalar_one_or_none()
            if order_model:
                tool_calls.append({"tool": "get_order", "args": {"order_code": order_code}})
                rows = await self._order_items(order_model.id)
                chosen = self._pick_items(rows, customer_text)
                if not chosen:
                    names = ", ".join(name for _, name in rows)
                    return (
                        f"Đơn {order_code} có các sản phẩm: {names}. Quý khách muốn trả sản phẩm nào ạ?",
                        tool_calls,
                        None,
                    )
                reason = self._reason_from(customer_text)
                if reason is None:
                    return ("Quý khách cho em biết lý do muốn trả hàng là gì ạ?", tool_calls, None)

                item_ids = [str(i.id) for i in chosen]
                tool_calls.append({
                    "tool": "check_return_eligibility",
                    "args": {"order_code": order_code, "item_ids": item_ids, "reason_code": reason.value},
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
                        "args": {"order_code": order_code, "items": items_payload, "reason_code": reason.value},
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
        if not order_code and any(w in msg_lower for w in ("hủy đơn", "huỷ đơn", "cancel")):
            return (
                "Quý khách vui lòng cho em xin mã đơn hàng cần hủy, hoặc cho biết đơn thứ mấy "
                "trong danh sách đơn gần đây ạ?",
                tool_calls,
                None,
            )
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
            tool_calls.append({"tool": "search_policy", "args": {"query": user_message}})
            return (
                "Theo quy định đổi trả [POL-RETURN-01], cửa hàng hỗ trợ đổi kích cỡ (size) sản phẩm tương đương trong vòng 15 ngày nếu sản phẩm còn hàng trong kho.",
                tool_calls,
                None,
            )

        # 4. Order Lookup / Tracking
        if order_code:
            try:
                order_dict = await self.order_service.get_order_for_principal(self.principal, order_code)
                tool_calls.append({"tool": "get_order", "args": {"order_code": order_code}})
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
        if any(w in msg_lower for w in self._POLICY_WORDS):
            tool_calls.append({"tool": "search_policy", "args": {"query": user_message}})
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
