"""Curated demo scenarios: one hand-built case per business flow.

The bulk generator in ``seeder.py`` produces volume; this module produces *coverage*. Every case has
a fixed code (``SL-DEMO01`` ...) so a demo, a screenshot or a manual test can name it, and every case
is built relative to ``now`` so the time windows (7 days change-of-mind, 15 days defect, 30 minute
proposal) behave the same whenever the seed runs.

Accounts: ``customer1`` is the main demo customer. It keeps at most two return requests in the last 30
days so the ``many_returns`` risk flag (3) never fires and the auto-approve path stays demonstrable.
``customer2`` is a new account with a high-value order (flag ``new_account_high_value``); ``customer3``
has four recent returns (flag ``many_returns``). ``customer4`` and ``customer5`` own the cases that are
already waiting in the staff portal (approvals, warehouse, handoff ticket).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.domain.policies.refund_calc import calculate_allocated_discounts
from shopagent.infra.db.tables import (
    ApprovalRequestModel,
    ConversationModel,
    CustomerModel,
    EvidenceFileModel,
    MessageModel,
    OrderItemModel,
    OrderModel,
    PaymentModel,
    ProductModel,
    ProductVariantModel,
    RefundModel,
    ReturnItemModel,
    ReturnRequestModel,
    ShipmentEventModel,
    ShipmentModel,
    TicketModel,
)

STAFF_AGENT = uuid.UUID(int=1)
STAFF_SUPERVISOR = uuid.UUID(int=2)


def _uid(n: int) -> uuid.UUID:
    return uuid.UUID(int=0xD000_0000 + n)


# (key, name, category, flags, [(sku, size, color, price, stock)])
_PRODUCTS: list[tuple[str, str, str, list[str], list[tuple[str, str, str, int, int]]]] = [
    ("tee", "Áo thun cotton basic", "fashion", [], [("DEMO-TEE-M", "M", "Trắng", 199000, 80), ("DEMO-TEE-L", "L", "Trắng", 199000, 0)]),
    ("jacket", "Áo khoác dù chống nắng", "fashion", [], [("DEMO-JKT-M", "M", "Đen", 349000, 40)]),
    ("sale", "Váy xả kho (hàng thanh lý)", "fashion", ["final_sale"], [("DEMO-SAL-M", "M", "Xanh", 129000, 10)]),
    ("lipstick", "Son lì nguyên seal", "cosmetics", ["sealed_cosmetic"], [("DEMO-LIP-01", "", "Đỏ", 259000, 60)]),
    ("underwear", "Bộ đồ lót cotton", "fashion", ["hygiene"], [("DEMO-UND-M", "M", "Be", 179000, 50)]),
    ("earbuds", "Tai nghe Bluetooth", "electronics_accessories", [], [("DEMO-EAR-01", "", "Đen", 890000, 25)]),
    ("phone", "Điện thoại Galaxy A-series", "electronics_accessories", [], [("DEMO-PHN-128", "128GB", "Đen", 6490000, 12)]),
    ("lamp", "Đèn ngủ để bàn", "home_living", [], [("DEMO-LMP-01", "", "Trắng", 450000, 30)]),
]


@dataclass
class _Line:
    sku: str
    qty: int = 1


@dataclass
class _Case:
    code: str
    customer: int
    status: str
    method: str
    lines: list[_Line]
    placed_days_ago: float
    delivered_days_ago: float | None = None
    discount: int = 0
    shipment: list[tuple[str, str, float]] = field(default_factory=list)  # (status, location, days ago)
    note: str = ""


def _cases() -> list[_Case]:
    ship_events = [
        ("shipped", "Kho ShopLab, Quận 7, TP.HCM", 2.5),
        ("in_transit", "Trung tâm khai thác Bình Dương", 1.6),
        ("out_for_delivery", "Bưu cục Thủ Đức", 0.2),
    ]
    return [
        # Cancel flow
        _Case("SL-DEMO01", 1, "pending_payment", "bank_transfer", [_Line("DEMO-TEE-M")], 0.2, note="Hủy tự phục vụ: chưa thanh toán"),
        _Case("SL-DEMO02", 1, "confirmed", "ewallet", [_Line("DEMO-JKT-M")], 0.4, note="Hủy tự phục vụ: đã thanh toán, hoàn về ví"),
        _Case("SL-DEMO03", 1, "packing", "card", [_Line("DEMO-EAR-01")], 0.8, note="Hủy khi đang đóng gói: cần nhân viên duyệt"),
        _Case("SL-DEMO04", 1, "shipped", "ewallet", [_Line("DEMO-LMP-01", 2)], 2.8, shipment=ship_events, note="Đang giao: xem hành trình, không hủy được"),
        _Case("SL-DEMO05", 1, "cancelled", "ewallet", [_Line("DEMO-TEE-M", 2)], 6.0, note="Đã hủy, đã hoàn tiền"),
        # Return eligibility windows
        _Case("SL-DEMO06", 1, "delivered", "ewallet", [_Line("DEMO-JKT-M")], 4.5, 2.0, note="Giao 2 ngày: đổi ý trả được, hoàn tự động dưới 500.000 đ"),
        _Case("SL-DEMO07", 1, "delivered", "card", [_Line("DEMO-EAR-01")], 13.0, 10.0, note="Giao 10 ngày: quá hạn đổi ý (7), còn hạn nếu hàng lỗi (15)"),
        _Case("SL-DEMO08", 1, "delivered", "ewallet", [_Line("DEMO-TEE-M")], 24.0, 20.0, note="Giao 20 ngày: quá mọi hạn đổi trả"),
        _Case("SL-DEMO09", 1, "delivered", "ewallet", [_Line("DEMO-LIP-01"), _Line("DEMO-UND-M")], 6.0, 3.0, note="Mỹ phẩm nguyên seal và đồ lót: loại trừ khi đổi ý"),
        _Case("SL-DEMO10", 1, "delivered", "bank_transfer", [_Line("DEMO-SAL-M")], 7.0, 4.0, note="Hàng thanh lý (final_sale): không đổi ý"),
        _Case("SL-DEMO11", 1, "delivered", "card", [_Line("DEMO-PHN-128")], 9.0, 5.0, note="Hàng lỗi, 6,49 triệu: cần bằng chứng, hoàn trên 2 triệu cần trưởng ca"),
        _Case("SL-DEMO12", 1, "delivered", "ewallet", [_Line("DEMO-EAR-01"), _Line("DEMO-TEE-M", 2)], 8.0, 5.0, discount=50000, note="Nhiều dòng có chia giảm giá: trả một phần"),
        _Case("SL-DEMO13", 1, "delivered", "cod", [_Line("DEMO-TEE-M")], 6.0, 3.0, note="Đổi cỡ: M còn hàng, L hết hàng"),
        # Staff workflow: states that already exist when the portal opens
        _Case("SL-DEMO14", 4, "delivered", "ewallet", [_Line("DEMO-LMP-01")], 9.0, 6.0, note="Phiếu RT-DEMO14: chờ nhân viên duyệt cổng A"),
        _Case("SL-DEMO15", 1, "delivered", "card", [_Line("DEMO-EAR-01")], 10.0, 7.0, note="Phiếu RT-DEMO15: chờ khách gửi hàng, kho chưa nhận"),
        _Case("SL-DEMO16", 4, "delivered", "ewallet", [_Line("DEMO-JKT-M")], 11.0, 8.0, note="Phiếu RT-DEMO16: kho đã nhận, chờ kiểm hàng"),
        _Case("SL-DEMO17", 1, "delivered", "ewallet", [_Line("DEMO-LMP-01")], 15.0, 12.0, note="Phiếu RT-DEMO17: hoàn tất, RF-DEMO17 đã giải ngân"),
        _Case("SL-DEMO18", 5, "delivered", "card", [_Line("DEMO-PHN-128")], 14.0, 11.0, note="Phiếu RT-DEMO18: kiểm đạt, RF-DEMO18 6,49 triệu chờ trưởng ca (cổng B)"),
        # Risk flags
        _Case("SL-DEMO19", 2, "delivered", "card", [_Line("DEMO-PHN-128")], 3.0, 1.0, note="Tài khoản mới 3 ngày, đơn trên 2 triệu: cờ new_account_high_value"),
        _Case("SL-DEMO20", 3, "delivered", "ewallet", [_Line("DEMO-JKT-M")], 6.0, 3.0, note="Khách đã có 3 phiếu trả trong 30 ngày: cờ many_returns"),
        _Case("SL-DEMO21", 3, "delivered", "ewallet", [_Line("DEMO-TEE-M")], 20.0, 16.0, note="Lịch sử trả của SL-DEMO20"),
        _Case("SL-DEMO22", 3, "delivered", "ewallet", [_Line("DEMO-LMP-01")], 22.0, 18.0, note="Lịch sử trả của SL-DEMO20"),
        _Case("SL-DEMO23", 3, "delivered", "ewallet", [_Line("DEMO-EAR-01")], 24.0, 20.0, note="Lịch sử trả của SL-DEMO20"),
        # COD
        _Case("SL-DEMO24", 1, "shipped", "cod", [_Line("DEMO-TEE-M")], 3.0, shipment=ship_events[:2], note="COD đang giao"),
    ]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def seed_demo_scenarios(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Add the curated products, orders, returns, approvals and a handoff conversation."""
    variants: dict[str, ProductVariantModel] = {}
    n = 0
    for p_idx, (_, name, cat, flags, vs) in enumerate(_PRODUCTS, start=1):
        prod = ProductModel(id=_uid(p_idx), name=name, category=cat, return_flags=flags, created_at=now - timedelta(days=200))
        session.add(prod)
        for sku, size, color, price, stock in vs:
            n += 1
            attrs = {k: v for k, v in (("size", size), ("color", color)) if v}
            var = ProductVariantModel(id=_uid(100 + n), product_id=prod.id, sku=sku, attributes=attrs, price=price, stock=stock)
            variants[sku] = var
            session.add(var)
    await session.flush()

    # customer2 is a brand-new account; customer1/3 keep their bulk-generated age.
    for cust_no, age_days in ((2, 3),):
        cust = await session.get(CustomerModel, uuid.UUID(int=1000 + cust_no))
        if cust is not None:
            cust.created_at = now - timedelta(days=age_days)

    orders: dict[str, OrderModel] = {}
    items: dict[str, list[OrderItemModel]] = {}
    for i, case in enumerate(_cases(), start=1):
        cust_id = uuid.UUID(int=1000 + case.customer)
        chosen = [(variants[ln.sku], ln.qty) for ln in case.lines]
        subtotal = sum(v.price * q for v, q in chosen)
        shipping = 0 if subtotal >= 500000 else 30000
        total = subtotal - case.discount + shipping
        paid = case.status not in ("pending_payment", "cancelled") and (case.method != "cod" or case.status == "delivered")
        placed_at = now - timedelta(days=case.placed_days_ago)
        if case.status == "pending_payment":
            pay_status, paid_amount = "unpaid", 0
        elif case.status == "cancelled":
            pay_status, paid_amount = ("refunded", total) if case.method != "cod" else ("unpaid", 0)
        elif paid:
            pay_status, paid_amount = "paid", total
        else:
            pay_status, paid_amount = "unpaid", 0  # COD collected on delivery
        order = OrderModel(
            id=_uid(1000 + i), code=case.code, customer_id=cust_id, status=case.status, payment_method=case.method,
            payment_status=pay_status, subtotal=subtotal, discount_total=case.discount, shipping_fee=shipping, total=total,
            paid_amount=paid_amount, refunded_amount=total if pay_status == "refunded" else 0, channel="web", note=case.note,
            policy_version="2026-11-01", placed_at=placed_at,
            delivered_at=now - timedelta(days=case.delivered_days_ago) if case.delivered_days_ago is not None else None,
            created_at=placed_at, updated_at=placed_at,
        )
        session.add(order)
        orders[case.code] = order
        allocated = calculate_allocated_discounts([{"unit_price": v.price, "qty": q} for v, q in chosen], case.discount)
        items[case.code] = []
        for j, ((v, q), alloc) in enumerate(zip(chosen, allocated, strict=True), start=1):
            it = OrderItemModel(id=_uid(5000 + i * 10 + j), order_id=order.id, variant_id=v.id, qty=q, unit_price=v.price, allocated_discount=alloc)
            items[case.code].append(it)
            session.add(it)

        if pay_status in ("paid", "refunded") and case.method != "cod":
            session.add(PaymentModel(id=_uid(9000 + i), order_id=order.id, gateway=case.method, gateway_txn_id=f"DEMO-TXN-{i:04d}", amount=total, status="succeeded", mode="simulated", created_at=placed_at))

        events = case.shipment
        if not events and case.status == "delivered":
            d = case.delivered_days_ago or 0
            events = [("shipped", "Kho ShopLab, Quận 7, TP.HCM", d + 2.5), ("in_transit", "Trung tâm khai thác", d + 1.2), ("delivered", "Giao thành công cho người nhận", d)]
        if events:
            ship = ShipmentModel(id=_uid(7000 + i), order_id=order.id, carrier="ShopLab Logistics", tracking_code=f"SLG{i:06d}VN", status=events[-1][0], direction="outbound", created_at=now - timedelta(days=events[0][2]))
            session.add(ship)
            await session.flush()
            for k, (st, loc, ago) in enumerate(events):
                session.add(ShipmentEventModel(id=_uid(8000 + i * 10 + k), shipment_id=ship.id, status=st, location=loc, occurred_at=now - timedelta(days=ago)))
    await session.flush()

    # Returns: (code, case, status, reason, resolution, evidence photos)
    returns: dict[str, ReturnRequestModel] = {}

    def add_return(code: str, case_code: str, status: str, reason: str, photos: int, *, age_days: float, flags: list[str] | None = None) -> ReturnRequestModel:
        order = orders[case_code]
        r = ReturnRequestModel(
            id=_uid(20000 + len(returns) + 1), code=code, order_id=order.id, customer_id=order.customer_id, reason_code=reason,
            resolution="refund", status=status, risk_flags=flags or [], policy_version="2026-11-01",
            deadline_ship_back=now + timedelta(days=3) if status in ("awaiting_return", "pending_review") else None,
            created_at=now - timedelta(days=age_days), updated_at=now - timedelta(days=age_days),
        )
        session.add(r)
        returns[code] = r
        for it in items[case_code]:
            session.add(ReturnItemModel(id=uuid.uuid4(), return_id=r.id, order_item_id=it.id, qty=it.qty, inspection_result="accepted" if status in ("accepted", "closed") else "pending"))
            it.returned_qty = it.qty
        for p in range(1, photos + 1):
            path = f"demo/{code}/photo-{p}.jpg"
            session.add(EvidenceFileModel(id=uuid.uuid4(), return_id=r.id, kind="photo", path=path, sha256=_sha(path), size=184_320, uploaded_by="customer", created_at=now - timedelta(days=age_days)))
        return r

    r14 = add_return("RT-DEMO14", "SL-DEMO14", "pending_review", "defective", 2, age_days=0.5)
    add_return("RT-DEMO15", "SL-DEMO15", "awaiting_return", "change_of_mind", 0, age_days=1.0)
    add_return("RT-DEMO16", "SL-DEMO16", "received", "defective", 3, age_days=2.0)
    r17 = add_return("RT-DEMO17", "SL-DEMO17", "accepted", "damaged_in_transit", 2, age_days=4.0)
    r18 = add_return("RT-DEMO18", "SL-DEMO18", "accepted", "defective", 2, age_days=3.0)
    add_return("RT-DEMO20", "SL-DEMO20", "rejected", "change_of_mind", 0, age_days=1.0)
    add_return("RT-DEMO21", "SL-DEMO21", "accepted", "change_of_mind", 0, age_days=12.0)
    add_return("RT-DEMO22", "SL-DEMO22", "accepted", "change_of_mind", 0, age_days=9.0)
    add_return("RT-DEMO23", "SL-DEMO23", "accepted", "change_of_mind", 0, age_days=6.0)
    await session.flush()

    def breakdown(case_code: str) -> dict[str, object]:
        its = items[case_code]
        net = sum(it.unit_price * it.qty - it.allocated_discount for it in its)
        return {"items_subtotal": sum(it.unit_price * it.qty for it in its), "total_allocated_discount": sum(it.allocated_discount for it in its), "shipping_fee_deduction": 0, "net_refundable": net}

    net17 = int(breakdown("SL-DEMO17")["net_refundable"])  # type: ignore[call-overload]
    net18 = int(breakdown("SL-DEMO18")["net_refundable"])  # type: ignore[call-overload]
    session.add(RefundModel(id=_uid(30001), code="RF-DEMO17", order_id=orders["SL-DEMO17"].id, return_id=r17.id, amount=net17, breakdown=breakdown("SL-DEMO17"), method="original", status="succeeded", gateway_txn_id="DEMO-RFD-17", attempts=1, created_at=now - timedelta(days=3), updated_at=now - timedelta(days=3)))
    orders["SL-DEMO17"].refunded_amount = net17
    orders["SL-DEMO17"].payment_status = "partially_refunded" if net17 < orders["SL-DEMO17"].paid_amount else "refunded"
    rf18 = RefundModel(id=_uid(30002), code="RF-DEMO18", order_id=orders["SL-DEMO18"].id, return_id=r18.id, amount=net18, breakdown=breakdown("SL-DEMO18"), method="original", status="pending_approval", attempts=0, created_at=now - timedelta(days=1), updated_at=now - timedelta(days=1))
    session.add(rf18)
    await session.flush()

    # Staff queue: gate A for RT-DEMO14 (agent), gate B for RF-DEMO18 (>2.000.000 đ, supervisor).
    session.add(ApprovalRequestModel(id=_uid(40001), subject_type="return_request", subject_id=r14.id, gate="A_return", required_role="agent", status="pending", requested_at=now - timedelta(hours=12)))
    session.add(ApprovalRequestModel(id=_uid(40002), subject_type="refund", subject_id=rf18.id, gate="B_refund", required_role="supervisor", status="pending", requested_at=now - timedelta(hours=20), requested_by=STAFF_AGENT))
    # A decided approval so the audit trail is not empty.
    session.add(ApprovalRequestModel(id=_uid(40003), subject_type="return_request", subject_id=r17.id, gate="A_return", required_role="agent", status="approved", requested_at=now - timedelta(days=4), decided_by=STAFF_AGENT, decided_at=now - timedelta(days=3, hours=20), note="Ảnh khớp mô tả: hộp móp, đèn vỡ"))

    # A handoff: conversation waiting for a human, with a ticket in the staff queue.
    conv = ConversationModel(id=_uid(50001), customer_id=uuid.UUID(int=1005), mode="waiting_human", summary="Khách khiếu nại đơn SL-DEMO18, yêu cầu gặp nhân viên.", last_message_seq=3, last_event_seq=0, created_at=now - timedelta(hours=3), updated_at=now - timedelta(hours=2))
    session.add(conv)
    await session.flush()
    for seq, role, text in (
        (1, "customer", "Tại sao điện thoại SL-DEMO18 của mình chưa được hoàn tiền? Đã 3 ngày rồi."),
        (2, "assistant", "Khoản hoàn 6.490.000 đ của đơn SL-DEMO18 vượt hạn mức tự duyệt nên đang chờ trưởng ca xem xét. Tôi sẽ chuyển anh/chị cho nhân viên để được hỗ trợ trực tiếp."),
        (3, "customer", "Vậy cho mình gặp nhân viên nhé."),
    ):
        session.add(MessageModel(id=uuid.uuid4(), conversation_id=conv.id, seq=seq, role=role, content=text, citations=[], created_at=now - timedelta(hours=3) + timedelta(minutes=seq)))
    session.add(TicketModel(id=_uid(60001), code="TK-DEMO01", conversation_id=conv.id, customer_id=uuid.UUID(int=1005), reason_code="customer_request", priority="high", status="open", agent_summary="Hoàn tiền 6,49 triệu chờ trưởng ca; khách hỏi tiến độ và xin gặp nhân viên.", context={"order_code": "SL-DEMO18", "refund_code": "RF-DEMO18"}, created_at=now - timedelta(hours=2)))

    await session.flush()
    return {"demo_orders": len(orders), "demo_returns": len(returns), "demo_products": len(_PRODUCTS)}
