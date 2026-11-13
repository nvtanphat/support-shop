"""The 11 official domain tool implementations for Shop Support Agent."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.tools.schemas import (
    CheckReturnEligibilityInput,
    CheckVariantStockInput,
    EscalateToHumanInput,
    GetCaseStatusInput,
    GetOrderInput,
    ListMyOrdersInput,
    LookupOrderGuestInput,
    ProposeCancelOrderInput,
    ProposeReturnInput,
    SearchPolicyInput,
    TrackShipmentInput,
)
from shopagent.core.clock import get_clock
from shopagent.core.config import get_app_config
from shopagent.core.errors import AppError, ForbiddenError, NotFoundError
from shopagent.core.principal import Principal
from shopagent.domain.services.cancellations import CancellationService
from shopagent.domain.services.orders import OrderService
from shopagent.domain.services.returns import ReturnService
from shopagent.domain.services.tickets import TicketService
from shopagent.infra.db.tables import (
    OrderModel,
    ProductVariantModel,
    RefundModel,
    ReturnRequestModel,
    ShipmentEventModel,
    ShipmentModel,
    TicketModel,
)
from shopagent.rag.reranker import RerankerUnavailableError
from shopagent.rag.retriever import PolicyIndexUnavailableError, PolicyRetriever

logger = logging.getLogger(__name__)


def _order_not_found(order_code: str) -> dict[str, Any]:
    """The same answer for "no such order" and "not yours", so order codes cannot be probed."""
    return {
        "error_code": "ORDER_NOT_FOUND",
        "message": f"Không tìm thấy đơn hàng '{order_code}' trong tài khoản của quý khách.",
    }


_CASE_NOT_FOUND = {"error_code": "CASE_NOT_FOUND", "message": "Không tìm thấy hồ sơ với mã này trong tài khoản của quý khách."}
_GUEST_VERIFICATION_REQUIRED = {
    "error_code": "GUEST_VERIFICATION_REQUIRED",
    "message": "Quý khách cần xác minh số điện thoại đặt hàng qua mã OTP để xem thông tin đơn hàng này.",
    "hint": "Mời khách bấm vào nút 'Xác minh đơn hàng' trên màn hình chat.",
}

def _within_budget(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Best-ranked clauses whose text fits the per-call budget; the first is always kept.

    The model's input window is small once the system prompt and tool schemas are counted, so a corpus of longer
    clauses must not fill it with lower-ranked text. A clause is dropped whole, never cut, so what the model reads is
    always a complete clause it may cite.
    """
    limit = int((get_app_config().get("retrieval") or {}).get("max_result_chars", 4000))
    kept: list[dict[str, Any]] = []
    used = 0
    for match in matches:
        length = len(str(match.get("text", "")))
        if kept and used + length > limit:
            break
        kept.append(match)
        used += length
    return kept


# -------------------------------------------------------------------------
# Tool Factory Functions
# -------------------------------------------------------------------------
def create_tools(
    session: AsyncSession,
    principal: Principal,
    conversation_id: uuid.UUID,
    retrieved_clauses: list[str] | None = None,
    proposed_actions_out: list[dict[str, Any]] | None = None,
) -> list[StructuredTool]:
    """Create and return the 11 domain tools bound to the current session and principal."""
    order_service = OrderService(session)
    return_service = ReturnService(session)
    cancellation_service = CancellationService(session)
    ticket_service = TicketService(session)
    retriever = PolicyRetriever(session)

    # Tool 1: search_policy
    async def search_policy(query: str, as_of: str | None = None) -> dict[str, Any]:
        """Tra cứu điều khoản chính sách đổi trả, bảo hành, hủy đơn, hoàn tiền của cửa hàng."""
        if as_of:
            try:
                as_of_dt = datetime.fromisoformat(as_of.strip().replace("Z", "+00:00"))
            except ValueError:
                return {
                    "status": "invalid_request",
                    "error_code": "INVALID_AS_OF",
                    "message": f"as_of '{as_of}' không phải thời điểm ISO hợp lệ; bỏ as_of để dùng chính sách hiện hành.",
                    "results": [],
                }
        else:
            as_of_dt = get_clock().now()
        try:
            matches = await retriever.retrieve(query=query, top_k=4, as_of=as_of_dt)
        except (PolicyIndexUnavailableError, RerankerUnavailableError) as e:
            return {
                "status": "index_unavailable",
                "error_code": "POLICY_INDEX_UNAVAILABLE",
                "message": f"Kho chính sách chưa sẵn sàng ({e}). Không được trả lời nội dung chính sách.",
                "results": [],
            }
        except SQLAlchemyError as e:
            logger.error("policy_retrieval_db_error error=%s", e)
            return {
                "status": "db_error",
                "error_code": "POLICY_DB_ERROR",
                "message": "Không thể tra cứu cơ sở dữ liệu chính sách lúc này. Không được trả lời nội dung chính sách.",
                "results": [],
            }

        if not matches:
            return {
                "status": "no_evidence",
                "message": (
                    f"Không tìm thấy điều khoản chính sách nào phù hợp với '{query}'. "
                    "Không được trả lời từ trí nhớ: hãy nói rõ chưa có thông tin và đề nghị chuyển nhân viên nếu khách cần."
                ),
                "results": [],
            }

        matches = _within_budget(matches)
        if retrieved_clauses is not None:
            retrieved_clauses.extend(m["clause_id"] for m in matches)
        return {
            "status": "success",
            "query": query,
            "as_of": as_of_dt.isoformat(),
            "results": matches,
            "policy_versions": sorted({m["version"] for m in matches}),
            "note": "Chỉ dùng nội dung điều khoản trả về làm căn cứ; điều khoản không trả lời trực tiếp câu hỏi thì không được dùng.",
        }

    # Tool 2: lookup_order_guest
    async def lookup_order_guest(order_code: str) -> dict[str, Any]:
        """Tra cứu đơn hàng cho khách vãng lai. Chỉ thành công khi khách đã xác minh quyền xem đơn qua OTP."""
        if not principal.is_guest:
            return {"error_code": "INVALID_PRINCIPAL", "message": "Công cụ này chỉ dùng cho khách chưa đăng nhập (guest)."}
        try:
            return await order_service.get_order_for_principal(principal, order_code)
        except (ForbiddenError, NotFoundError):
            # Unknown and unverified orders look the same to a guest.
            return dict(_GUEST_VERIFICATION_REQUIRED)
        except AppError as e:
            return {"error_code": e.error_code, "message": str(e)}

    # Tool 3: list_my_orders
    async def list_my_orders(limit: int = 5) -> dict[str, Any]:
        """Xem danh sách các đơn hàng gần đây của khách hàng đã đăng nhập."""
        try:
            orders = await order_service.list_orders_for_principal(principal, limit=limit)
            return {"orders": orders, "count": len(orders)}
        except AppError as e:
            return {"error_code": e.error_code, "message": str(e)}

    # Tool 4: get_order
    async def get_order(order_code: str) -> dict[str, Any]:
        """Xem chi tiết đầy đủ của đơn hàng (dòng sản phẩm, item_id, mốc thời gian, thanh toán, vận chuyển)."""
        try:
            return await order_service.get_order_for_principal(principal, order_code)
        except (ForbiddenError, NotFoundError):
            return _order_not_found(order_code)
        except AppError as e:
            return {"error_code": e.error_code, "message": str(e)}

    # Tool 5: track_shipment
    async def track_shipment(order_code: str) -> dict[str, Any]:
        """Xem lịch trình và các sự kiện vận chuyển chi tiết của đơn hàng."""
        order_model = await order_service.order_repo.get_by_code(order_code)
        if not order_model or not principal.can_access_order(order_model.customer_id, order_model.id):
            return _order_not_found(order_code)

        stmt = select(ShipmentModel).where(ShipmentModel.order_id == order_model.id)
        res = await session.execute(stmt)
        shipments = res.scalars().all()
        result_shipments = []
        for s in shipments:
            ev_stmt = select(ShipmentEventModel).where(ShipmentEventModel.shipment_id == s.id)
            ev_res = await session.execute(ev_stmt)
            events = ev_res.scalars().all()
            result_shipments.append({
                "tracking_code": s.tracking_code,
                "carrier": s.carrier,
                "status": s.status,
                "events": [{"status": ev.status, "location": ev.location, "at": ev.occurred_at.isoformat()} for ev in events],
            })
        return {"order_code": order_code, "shipments": result_shipments}

    # Tool 6: check_return_eligibility
    async def check_return_eligibility(
        order_code: str,
        item_ids: list[str],
        reason_code: str,
        resolution: str = "refund",
    ) -> dict[str, Any]:
        """Kiểm tra điều kiện đổi trả theo chính sách và ước tính khoản tiền hoàn."""
        try:
            res = await return_service.check_eligibility_for_principal(
                principal=principal,
                order_code=order_code,
                item_ids=item_ids,
                reason_code=reason_code,
                resolution=resolution,
            )
            if res.get("clause_id") and retrieved_clauses is not None:
                retrieved_clauses.append(res["clause_id"])
            # Echo what was checked so a later propose_return can prove it follows this exact check.
            return {
                **res,
                "checked": {"order_code": order_code, "item_ids": list(item_ids), "reason_code": reason_code, "resolution": resolution},
            }
        except AppError as e:
            return {"error_code": e.error_code, "message": str(e)}

    # Tool 7: check_variant_stock
    async def check_variant_stock(sku: str) -> dict[str, Any]:
        """Kiểm tra tồn kho của một phân loại và liệt kê các phân loại khác (size, màu) của cùng sản phẩm.

        Gọi với SKU của sản phẩm khách đang có (lấy từ get_order) để biết SKU thật của size/màu khách muốn
        đổi sang; không tự đoán SKU.
        """
        stmt = select(ProductVariantModel).where(ProductVariantModel.sku == sku)
        res = await session.execute(stmt)
        var = res.scalar_one_or_none()
        if not var:
            return {"sku": sku, "in_stock": False, "stock": 0, "message": f"Không tìm thấy phân loại {sku}."}
        siblings = (
            await session.execute(
                select(ProductVariantModel).where(ProductVariantModel.product_id == var.product_id).order_by(ProductVariantModel.sku)
            )
        ).scalars().all()
        return {
            "sku": sku,
            "in_stock": var.stock > 0,
            "stock": var.stock,
            "price": var.price,
            "attributes": var.attributes,
            # Same product, other sizes/colours: the only SKUs an exchange may go to (same price required).
            "variants": [
                {"sku": v.sku, "attributes": v.attributes, "price": v.price, "stock": v.stock, "in_stock": v.stock > 0}
                for v in siblings
            ],
        }

    # Tool 8: get_case_status
    async def get_case_status(case_code: str | None = None) -> dict[str, Any]:
        """Xem tiến độ của yêu cầu trả hàng, phiếu hoàn tiền hoặc phiếu hỗ trợ."""
        if case_code:
            code_upper = case_code.strip().upper()
            if code_upper.startswith("RT-"):
                stmt_ret = select(ReturnRequestModel).where(ReturnRequestModel.code == code_upper)
                res_ret = await session.execute(stmt_ret)
                ret = res_ret.scalar_one_or_none()
                if ret:
                    if not principal.can_access_order(ret.customer_id, ret.order_id):
                        return dict(_CASE_NOT_FOUND)
                    return {
                        "case_type": "return_request",
                        "code": ret.code,
                        "status": ret.status,
                        "reason": ret.reason_code,
                        "created_at": ret.created_at.isoformat(),
                        "deadline_ship_back": ret.deadline_ship_back.isoformat() if ret.deadline_ship_back else None,
                    }
            elif code_upper.startswith("RF-"):
                stmt_rf = select(RefundModel).where(RefundModel.code == code_upper)
                res_rf = await session.execute(stmt_rf)
                rf = res_rf.scalar_one_or_none()
                if rf:
                    order = await session.get(OrderModel, rf.order_id)
                    if not order or not principal.can_access_order(order.customer_id, order.id):
                        return dict(_CASE_NOT_FOUND)
                    return {
                        "case_type": "refund",
                        "code": rf.code,
                        "amount": rf.amount,
                        "status": rf.status,
                        "created_at": rf.created_at.isoformat(),
                    }
            elif code_upper.startswith("TK-"):
                stmt_tk = select(TicketModel).where(TicketModel.code == code_upper)
                res_tk = await session.execute(stmt_tk)
                tk = res_tk.scalar_one_or_none()
                if tk:
                    is_allowed = (
                        principal.is_staff
                        or (principal.is_authenticated_customer and tk.customer_id == principal.customer_id)
                        or (tk.conversation_id == conversation_id)
                    )
                    if not is_allowed:
                        return dict(_CASE_NOT_FOUND)
                    return {
                        "case_type": "ticket",
                        "code": tk.code,
                        "status": tk.status,
                        "priority": tk.priority,
                        "created_at": tk.created_at.isoformat(),
                    }

        # If no code, list active cases for customer
        if principal.is_authenticated_customer:
            stmt_all_ret = select(ReturnRequestModel).where(ReturnRequestModel.customer_id == principal.customer_id)
            res_all_ret = await session.execute(stmt_all_ret)
            returns = res_all_ret.scalars().all()
            return {
                "active_returns": [{"code": r.code, "status": r.status, "reason": r.reason_code} for r in returns]
            }
        return {"error_code": "CASE_NOT_FOUND", "message": f"Không tìm thấy hồ sơ '{case_code}'."}

    # Tool 9: propose_cancel_order
    async def propose_cancel_order(order_code: str, reason: str = "customer_request") -> dict[str, Any]:
        """Tạo bản xem trước và thẻ đề xuất hủy đơn hàng để khách bấm xác nhận qua API."""
        try:
            prop = await cancellation_service.propose_cancellation(
                principal=principal,
                conversation_id=conversation_id,
                order_code=order_code,
                reason=reason,
            )
            if proposed_actions_out is not None:
                proposed_actions_out.append(prop)
            return {
                "action_id": prop["action_id"],
                "type": prop["type"],
                "preview": prop["preview"],
                "preview_hash": prop["preview_hash"],
                "expires_at": prop["expires_at"],
                "instruction": "Đã tạo thẻ đề xuất hủy đơn. Yêu cầu khách hàng kiểm tra thông tin và bấm 'Xác nhận hủy đơn' trên thẻ để hệ thống thực hiện.",
            }
        except AppError as e:
            return {"error_code": e.error_code, "message": str(e)}

    # Tool 10: propose_return
    async def propose_return(
        order_code: str,
        items: list[dict[str, Any]],
        reason_code: str,
        resolution: str = "refund",
        exchange_sku: str | None = None,
        refund_method: str = "original",
    ) -> dict[str, Any]:
        """Tạo bản xem trước và thẻ đề xuất đổi trả hàng để khách bấm xác nhận qua API."""
        try:
            prop = await return_service.propose_return(
                principal=principal,
                conversation_id=conversation_id,
                order_code=order_code,
                items=items,
                reason_code=reason_code,
                resolution=resolution,
                exchange_sku=exchange_sku,
                refund_method=refund_method,
            )
            if proposed_actions_out is not None:
                proposed_actions_out.append(prop)
            return {
                "action_id": prop["action_id"],
                "type": prop["type"],
                "preview": prop["preview"],
                "preview_hash": prop["preview_hash"],
                "expires_at": prop["expires_at"],
                "instruction": "Đã tạo thẻ đề xuất đổi trả. Yêu cầu khách hàng kiểm tra số tiền hoàn và hạn gửi hàng, sau đó bấm 'Xác nhận' trên thẻ.",
            }
        except AppError as e:
            return {"error_code": e.error_code, "message": str(e)}

    # Tool 11: escalate_to_human
    async def escalate_to_human(reason_code: str, summary: str) -> dict[str, Any]:
        """Tạo phiếu hỗ trợ khẩn và chuyển phiên chat cho chuyên viên chăm sóc khách hàng."""
        ticket = await ticket_service.create_ticket(
            principal=principal,
            conversation_id=conversation_id,
            reason_code=reason_code,
            agent_summary=summary,
            priority="high",
        )
        return {
            "ticket_code": ticket.code,
            "status": "open",
            "message": f"Đã tạo phiếu hỗ trợ #{ticket.code} và chuyển tiếp yêu cầu đến chuyên viên chăm sóc khách hàng. Chuyên viên sẽ liên hệ lại với bạn trong vòng 30 phút.",
            "estimated_response_minutes": 30,
        }

    # Wrap as LangChain StructuredTools
    t_search_policy = StructuredTool.from_function(
        coroutine=search_policy,
        name="search_policy",
        description="Tra cứu chính sách cửa hàng (đổi trả, hoàn tiền, hủy đơn, bảo hành).",
        args_schema=SearchPolicyInput,
    )
    t_lookup_guest = StructuredTool.from_function(
        coroutine=lookup_order_guest,
        name="lookup_order_guest",
        description="Tra cứu đơn hàng cho khách vãng lai (yêu cầu OTP).",
        args_schema=LookupOrderGuestInput,
    )
    t_list_orders = StructuredTool.from_function(
        coroutine=list_my_orders,
        name="list_my_orders",
        description="Xem danh sách đơn hàng gần đây của khách đã đăng nhập.",
        args_schema=ListMyOrdersInput,
    )
    t_get_order = StructuredTool.from_function(
        coroutine=get_order,
        name="get_order",
        description="Xem chi tiết đầy đủ đơn hàng (sản phẩm, số tiền, ngày giao, hành động được phép).",
        args_schema=GetOrderInput,
    )
    t_track_shipment = StructuredTool.from_function(
        coroutine=track_shipment,
        name="track_shipment",
        description="Theo dõi trạng thái và sự kiện vận chuyển của đơn hàng.",
        args_schema=TrackShipmentInput,
    )
    t_check_eligibility = StructuredTool.from_function(
        coroutine=check_return_eligibility,
        name="check_return_eligibility",
        description="Kiểm tra điều kiện đổi trả theo chính sách và ước tính khoản hoàn tiền.",
        args_schema=CheckReturnEligibilityInput,
    )
    t_check_stock = StructuredTool.from_function(
        coroutine=check_variant_stock,
        name="check_variant_stock",
        description="Khi khách muốn đổi size/màu: gọi với SKU sản phẩm khách đang có (từ get_order) để xem tồn kho và SKU của các phân loại khác cùng sản phẩm.",
        args_schema=CheckVariantStockInput,
    )
    t_get_case = StructuredTool.from_function(
        coroutine=get_case_status,
        name="get_case_status",
        description="Tra cứu tiến độ hồ sơ đổi trả, hoàn tiền, hoặc phiếu hỗ trợ.",
        args_schema=GetCaseStatusInput,
    )
    t_propose_cancel = StructuredTool.from_function(
        coroutine=propose_cancel_order,
        name="propose_cancel_order",
        description="Tạo đề xuất hủy đơn hàng để khách xác nhận (không tự ý hủy trực tiếp).",
        args_schema=ProposeCancelOrderInput,
    )
    t_propose_return = StructuredTool.from_function(
        coroutine=propose_return,
        name="propose_return",
        description="Tạo đề xuất trả hàng / hoàn tiền để khách xác nhận (không tự ý trả trực tiếp).",
        args_schema=ProposeReturnInput,
    )
    t_escalate = StructuredTool.from_function(
        coroutine=escalate_to_human,
        name="escalate_to_human",
        description="Bắt buộc gọi công cụ này để tạo Ticket trong cơ sở dữ liệu khi khách báo sự cố thanh toán (trừ tiền 2 lần, không có đơn), khiếu nại tranh chấp hoặc yêu cầu gặp nhân viên hỗ trợ trực tiếp.",
        args_schema=EscalateToHumanInput,
    )

    # Filter tools based on Principal (Section 6.2)
    if principal.is_guest:
        # Guests only see search_policy, lookup_order_guest, escalate_to_human
        return [t_search_policy, t_lookup_guest, t_escalate]
    else:
        # Authenticated customers see all tools except lookup_order_guest
        return [
            t_search_policy,
            t_list_orders,
            t_get_order,
            t_track_shipment,
            t_check_eligibility,
            t_check_stock,
            t_get_case,
            t_propose_cancel,
            t_propose_return,
            t_escalate,
        ]
