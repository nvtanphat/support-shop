"""Return and refund domain service."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock, to_utc
from shopagent.core.config import get_rules_config
from shopagent.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shopagent.core.ids import (
    generate_return_code,
    generate_uuid,
)
from shopagent.core.principal import Principal
from shopagent.core.security import compute_preview_hash
from shopagent.domain.models.entities import Order, OrderItem
from shopagent.domain.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PendingActionStatus,
    PendingActionType,
    ProductCategory,
    ReturnFlag,
    ReturnReason,
    ReturnResolution,
    ReturnStatus,
)
from shopagent.domain.policies.engine import (
    check_return_eligibility,
)
from shopagent.domain.policies.rules import PolicyRules
from shopagent.infra.db.repositories.action_repo import ActionRepository
from shopagent.infra.db.repositories.approval_repo import ApprovalRepository
from shopagent.infra.db.repositories.audit_repo import AuditRepository
from shopagent.infra.db.repositories.order_repo import OrderRepository
from shopagent.infra.db.repositories.outbox_repo import OutboxRepository
from shopagent.infra.db.repositories.refund_repo import RefundRepository
from shopagent.infra.db.repositories.return_repo import ReturnRepository
from shopagent.infra.db.tables import (
    ApprovalRequestModel,
    OrderModel,
    PendingActionModel,
    ProductVariantModel,
    ReturnItemModel,
    ReturnRequestModel,
)


class ReturnService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.order_repo = OrderRepository(session)
        self.return_repo = ReturnRepository(session)
        self.refund_repo = RefundRepository(session)
        self.action_repo = ActionRepository(session)
        self.approval_repo = ApprovalRepository(session)
        self.audit_repo = AuditRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.clock = get_clock()

    def _to_domain_order(self, o: OrderModel) -> Order:
        items = [
            OrderItem(
                id=it.id,
                order_id=it.order_id,
                variant_id=it.variant_id,
                sku=it.variant.sku if it.variant else getattr(it, "sku", ""),
                product_name=it.variant.product.name if it.variant and it.variant.product else getattr(it, "product_name", ""),
                qty=it.qty,
                unit_price=it.unit_price,
                allocated_discount=it.allocated_discount,
                returned_qty=it.returned_qty,
                exchanged=it.exchanged,
                category=ProductCategory.FASHION if not (it.variant and it.variant.product) else (
                    ProductCategory(it.variant.product.category) if it.variant.product.category in [c.value for c in ProductCategory] else ProductCategory.FASHION
                ),
                return_flags=[ReturnFlag(f) for f in (it.variant.product.return_flags if it.variant and it.variant.product else getattr(it, "return_flags", []))],
            )
            for it in o.items
        ]
        return Order(
            id=o.id,
            code=o.code,
            customer_id=o.customer_id,
            status=OrderStatus(o.status),
            payment_method=PaymentMethod(o.payment_method),
            payment_status=PaymentStatus(o.payment_status),
            subtotal=o.subtotal,
            discount_total=o.discount_total,
            shipping_fee=o.shipping_fee,
            total=o.total,
            paid_amount=getattr(o, "paid_amount", o.total),
            refunded_amount=getattr(o, "refunded_amount", 0),
            channel=o.channel,
            note=o.note,
            policy_version=o.policy_version,
            placed_at=o.placed_at,
            delivered_at=o.delivered_at,
            items=items,
        )

    async def check_eligibility_for_principal(
        self,
        principal: Principal,
        order_code: str,
        item_ids: list[str],
        reason_code: str,
        resolution: str = "refund",
    ) -> dict[str, Any]:
        """Check return eligibility and compute estimated refund."""
        order_model = await self.order_repo.get_by_code(order_code)
        if not order_model:
            raise NotFoundError(f"Không tìm thấy đơn hàng '{order_code}'.", error_code="ORDER_NOT_FOUND")

        if not principal.can_access_order(order_model.customer_id, order_model.id):
            raise ForbiddenError("Bạn không có quyền truy cập đơn hàng này.", error_code="ORDER_ACCESS_DENIED")

        domain_order = self._to_domain_order(order_model)
        item_id_map = {str(it.id): it for it in domain_order.items}

        selected_items: list[tuple[OrderItem, int]] = []
        for i_id in item_ids:
            if i_id in item_id_map:
                it = item_id_map[i_id]
                selected_items.append((it, 1))

        rules = PolicyRules.model_validate(get_rules_config())
        reason = ReturnReason(reason_code)
        res_type = ReturnResolution(resolution)

        # Check eligibility
        result = check_return_eligibility(
            order=domain_order,
            items_to_return=selected_items,
            reason=reason,
            resolution=res_type,
            as_of=self.clock.now(),
            policy=rules,
        )

        return {
            "eligible": result.eligible,
            "decision_code": result.decision_code,
            "clause_id": result.clause_id,
            "message": result.message,
            "requires_evidence": result.requires_evidence,
            "min_photos": result.min_photos,
            "requires_video": result.requires_video,
            "estimated_refund": (
                {
                    "amount": result.estimated_refund.refundable_amount,
                    "explanation": result.estimated_refund.explanation,
                    "breakdown": result.estimated_refund.details,
                }
                if result.estimated_refund
                else None
            ),
            "ship_back_deadline": result.ship_back_deadline.isoformat() if result.ship_back_deadline else None,
        }

    async def _validate_exchange(
        self, selected_items: list[tuple[OrderItem, int]], exchange_sku: str | None, rules: PolicyRules
    ) -> None:
        """An exchange goes to a real variant of the same product, at the same price, that is in stock.

        The agent picks the SKU, so the domain must not trust it: without this check a model could propose
        swapping a T-shirt for a phone and the card would be created.
        """
        if not exchange_sku:
            raise ValidationError("Đổi hàng cần chọn phân loại mới (exchange_sku).", error_code="EXCHANGE_SKU_REQUIRED")
        target = (
            await self.session.execute(select(ProductVariantModel).where(ProductVariantModel.sku == exchange_sku.strip()))
        ).scalar_one_or_none()
        if target is None:
            raise NotFoundError(f"Không tìm thấy phân loại '{exchange_sku}'.", error_code="EXCHANGE_SKU_NOT_FOUND")
        wanted = 0
        for item, qty in selected_items:
            original = await self.session.get(ProductVariantModel, item.variant_id)
            if original is None:
                raise NotFoundError(f"Không tìm thấy phân loại gốc của {item.sku}.", error_code="ITEM_NOT_FOUND")
            if target.id == original.id:
                raise ValidationError("Phân loại mới trùng với phân loại đang có.", error_code="EXCHANGE_SAME_VARIANT")
            if rules.exchange_policy.same_product_only and target.product_id != original.product_id:
                raise ValidationError(
                    "Chỉ đổi sang phân loại khác (size, màu) của cùng sản phẩm.", error_code="EXCHANGE_DIFFERENT_PRODUCT",
                    hint="Xem điều khoản [POL-EXCHANGE-01].",
                )
            if rules.exchange_policy.same_price_only and target.price != original.price:
                raise ValidationError(
                    "Phân loại mới phải cùng giá với phân loại ban đầu.", error_code="EXCHANGE_PRICE_MISMATCH",
                    hint="Xem điều khoản [POL-EXCHANGE-01].",
                )
            wanted += qty
        if target.stock < wanted:
            raise ConflictError(f"Phân loại '{exchange_sku}' không đủ hàng để đổi.", error_code="EXCHANGE_OUT_OF_STOCK")

    async def propose_return(
        self,
        principal: Principal,
        conversation_id: uuid.UUID,
        order_code: str,
        items: list[dict[str, Any]],  # [{"item_id": str, "qty": int}]
        reason_code: str,
        resolution: str = "refund",
        exchange_sku: str | None = None,
        refund_method: str = "original",
    ) -> dict[str, Any]:
        """Propose return request for customer confirmation."""
        if not principal.is_authenticated_customer or principal.customer_id is None:
            raise ForbiddenError("Chỉ khách hàng sở hữu tài khoản mới có thể tạo yêu cầu đổi trả.")

        order_model = await self.order_repo.get_by_code(order_code)
        if not order_model:
            raise NotFoundError(f"Không tìm thấy đơn hàng '{order_code}'.", error_code="ORDER_NOT_FOUND")

        if order_model.customer_id != principal.customer_id:
            raise ForbiddenError("Bạn không có quyền thực hiện trên đơn hàng của người khác.", error_code="ORDER_ACCESS_DENIED")

        domain_order = self._to_domain_order(order_model)
        item_id_map = {str(it.id): it for it in domain_order.items}

        selected_items: list[tuple[OrderItem, int]] = []
        for it_dict in items:
            i_id = str(it_dict["item_id"])
            qty = it_dict.get("qty", 1)
            if i_id not in item_id_map:
                raise ValidationError(f"Mục hàng '{i_id}' không thuộc đơn hàng này.", error_code="ITEM_NOT_FOUND")
            selected_items.append((item_id_map[i_id], qty))

        rules = PolicyRules.model_validate(get_rules_config())
        reason = ReturnReason(reason_code)
        res_type = ReturnResolution(resolution)

        # Pre-verify eligibility
        eligibility = check_return_eligibility(
            order=domain_order,
            items_to_return=selected_items,
            reason=reason,
            resolution=res_type,
            as_of=self.clock.now(),
            policy=rules,
        )

        if not eligibility.eligible:
            raise ConflictError(
                f"Không đủ điều kiện đổi trả: {eligibility.message}",
                error_code=eligibility.decision_code,
                hint=f"Xem điều khoản trích dẫn [{eligibility.clause_id}].",
            )
        if res_type == ReturnResolution.EXCHANGE:
            await self._validate_exchange(selected_items, exchange_sku, rules)

        payload = {
            "order_id": str(order_model.id),
            "order_code": order_model.code,
            "items": [{"item_id": str(it.id), "qty": qty, "sku": it.sku} for it, qty in selected_items],
            "reason_code": reason.value,
            "resolution": res_type.value,
            "exchange_sku": exchange_sku,
            "refund_method": refund_method,
            "estimated_refund": eligibility.estimated_refund.refundable_amount if eligibility.estimated_refund else 0,
            "requires_evidence": eligibility.requires_evidence,
            "min_photos": eligibility.min_photos,
            "requires_video": eligibility.requires_video,
        }
        payload_hash = compute_preview_hash(payload)

        # Check existing active proposal
        existing = await self.action_repo.get_active_proposal(conversation_id, payload_hash)
        if existing and to_utc(existing.expires_at) > self.clock.now():
            return {
                "action_id": str(existing.id),
                "type": existing.type,
                "preview": existing.preview,
                "preview_hash": existing.payload_hash,
                "expires_at": existing.expires_at.isoformat(),
            }
        if existing is not None:
            # Expired but never confirmed or cancelled: retire it, or the new card would collide with it
            # on the unique (conversation, payload hash) index of live proposals.
            existing.status = PendingActionStatus.EXPIRED.value
            await self.session.flush()

        preview = {
            "title": f"Xác nhận yêu cầu {'đổi hàng' if res_type == ReturnResolution.EXCHANGE else 'trả hàng hoàn tiền'} {order_model.code}",
            "order_code": order_model.code,
            "resolution": res_type.value,
            "reason_code": reason.value,
            "items_count": sum(qty for _, qty in selected_items),
            "estimated_refund": eligibility.estimated_refund.refundable_amount if eligibility.estimated_refund else 0,
            "refund_explanation": eligibility.estimated_refund.explanation if eligibility.estimated_refund else None,
            "requires_evidence": eligibility.requires_evidence,
            "requires_video": eligibility.requires_video,
            "deadline_ship_back": eligibility.ship_back_deadline.isoformat() if eligibility.ship_back_deadline else None,
            "message": "Vui lòng kiểm tra kỹ chi tiết và nhấn Xác nhận trên thẻ này để gửi yêu cầu chính thức.",
        }

        now = self.clock.now()
        action = PendingActionModel(
            id=generate_uuid(),
            conversation_id=conversation_id,
            customer_id=principal.customer_id,
            type=PendingActionType.RETURN_REQUEST.value,
            payload=payload,
            payload_hash=payload_hash,
            preview=preview,
            status=PendingActionStatus.PROPOSED.value,
            presented_at=now,
            expires_at=now + timedelta(minutes=rules.pending_action_ttl_minutes),
        )
        await self.action_repo.save(action)

        return {
            "action_id": str(action.id),
            "type": action.type,
            "preview": preview,
            "preview_hash": payload_hash,
            "expires_at": action.expires_at.isoformat(),
        }

    async def execute_return(
        self, principal: Principal, action: PendingActionModel, preview_hash: str
    ) -> dict[str, Any]:
        """Execute return request inside transaction upon customer confirmation."""
        if action.payload_hash != preview_hash:
            raise ValidationError("Mã băm xem trước không khớp điều khoản đã xác nhận.", error_code="PREVIEW_HASH_MISMATCH")

        now = self.clock.now()
        if to_utc(action.expires_at) < to_utc(now):
            action.status = PendingActionStatus.EXPIRED.value
            await self.action_repo.save(action)
            raise ConflictError("Đề xuất đã hết hạn (30 phút).", error_code="ACTION_EXPIRED")

        payload = action.payload
        order_id = uuid.UUID(payload["order_id"])
        order_model = await self.order_repo.get_by_id(order_id)
        if not order_model:
            raise NotFoundError("Đơn hàng không tồn tại.", error_code="ORDER_NOT_FOUND")

        if order_model.customer_id != principal.customer_id:
            raise ForbiddenError("Bạn không sở hữu đơn hàng này.", error_code="ORDER_ACCESS_DENIED")

        domain_order = self._to_domain_order(order_model)
        item_id_map = {str(it.id): it for it in domain_order.items}

        selected_items: list[tuple[OrderItem, int]] = []
        for it_dict in payload["items"]:
            i_id = str(it_dict["item_id"])
            qty = it_dict["qty"]
            selected_items.append((item_id_map[i_id], qty))

        rules = PolicyRules.model_validate(get_rules_config())
        reason = ReturnReason(payload["reason_code"])
        res_type = ReturnResolution(payload["resolution"])

        # Re-check eligibility in transaction
        eligibility = check_return_eligibility(
            order=domain_order,
            items_to_return=selected_items,
            reason=reason,
            resolution=res_type,
            as_of=now,
            policy=rules,
        )

        if not eligibility.eligible:
            action.status = PendingActionStatus.FAILED.value
            await self.action_repo.save(action)
            raise ConflictError(f"Điều kiện đổi trả không còn thỏa mãn: {eligibility.message}", error_code=eligibility.decision_code)
        if res_type == ReturnResolution.EXCHANGE:
            try:  # stock may have run out since the card was shown
                await self._validate_exchange(selected_items, payload.get("exchange_sku"), rules)
            except (ConflictError, ValidationError, NotFoundError):
                action.status = PendingActionStatus.FAILED.value
                await self.action_repo.save(action)
                raise

        # Create ReturnRequest
        return_code = generate_return_code()
        initial_status = ReturnStatus.AWAITING_RETURN if eligibility.required_role == "auto" else ReturnStatus.PENDING_REVIEW

        return_req = ReturnRequestModel(
            id=generate_uuid(),
            code=return_code,
            order_id=order_model.id,
            customer_id=principal.customer_id,
            reason_code=reason.value,
            resolution=res_type.value,
            status=initial_status.value,
            risk_flags=eligibility.details.get("risk_flags", []),
            policy_version=order_model.policy_version,
            deadline_ship_back=eligibility.ship_back_deadline,
            created_at=now,
        )
        await self.return_repo.save(return_req)

        # Add return items and update order items returned_qty
        for it, qty in selected_items:
            ret_item = ReturnItemModel(
                id=generate_uuid(),
                return_id=return_req.id,
                order_item_id=it.id,
                qty=qty,
                inspection_result="pending",
            )
            self.session.add(ret_item)

            # Update order item model
            for db_item in order_model.items:
                if db_item.id == it.id:
                    db_item.returned_qty += qty
                    if res_type == ReturnResolution.EXCHANGE:
                        db_item.exchanged = True

        await self.session.flush()

        # Gate A Approval request if not auto
        if eligibility.required_role != "auto":
            approval = ApprovalRequestModel(
                id=generate_uuid(),
                subject_type="return_request",
                subject_id=return_req.id,
                gate=ApprovalGate.A_RETURN.value,
                required_role=eligibility.required_role,
                status=ApprovalStatus.PENDING.value,
                requested_at=now,
                note=f"Yêu cầu trả hàng cần duyệt ({reason.value}). Cần {eligibility.min_photos} ảnh.",
            )
            await self.approval_repo.save(approval)

        # Outbox event
        await self.outbox_repo.add_event(
            event_type="return.created",
            payload={
                "return_id": str(return_req.id),
                "return_code": return_req.code,
                "order_code": order_model.code,
                "status": return_req.status,
            },
            idempotency_key=f"return_created_{return_req.id}",
        )

        # Audit log
        await self.audit_repo.log(
            actor_type="customer",
            actor_id=str(principal.customer_id),
            action="return.created",
            subject_type="return_request",
            subject_id=str(return_req.id),
            before_state=None,
            after_state={"code": return_req.code, "status": return_req.status},
        )

        action.status = PendingActionStatus.CONFIRMED.value
        action.result = {"return_code": return_req.code, "status": return_req.status}
        await self.action_repo.save(action)

        return {
            "success": True,
            "return_code": return_req.code,
            "status": return_req.status,
            "requires_evidence": eligibility.requires_evidence,
            "deadline_ship_back": eligibility.ship_back_deadline.isoformat() if eligibility.ship_back_deadline else None,
            "message": (
                f"Yêu cầu trả hàng {return_req.code} đã được chấp thuận tự động. Bạn vui lòng gửi hàng về trước hạn."
                if initial_status == ReturnStatus.AWAITING_RETURN
                else f"Yêu cầu trả hàng {return_req.code} đã được ghi nhận và đang chờ nhân viên kiểm duyệt bằng chứng."
            ),
        }
