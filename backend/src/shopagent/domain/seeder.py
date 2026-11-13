"""Deterministic seed data generator for shop-support-agent.

Generates 300 customers, credentials, staff users, 120 products with their variants,
1,500 orders covering all states with payments and shipments, ~150 historical return requests
(with items, evidence and refunds), then the curated demo cases from ``demo_seed``.
Deterministic by seed and relative to specified reference timestamp (--now).
"""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.ids import (
    generate_uuid,
)
from shopagent.core.security import hash_password
from shopagent.domain.demo_seed import seed_demo_scenarios
from shopagent.domain.models.enums import (
    PaymentMethod,
    PaymentStatus,
    ProductCategory,
    ReturnFlag,
    ReturnReason,
    ReturnResolution,
    ReturnStatus,
)
from shopagent.domain.policies.refund_calc import calculate_allocated_discounts
from shopagent.infra.db.tables import (
    CustomerCredentialsModel,
    CustomerModel,
    EvidenceFileModel,
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
    StaffUserModel,
)

CATEGORIES = [
    (ProductCategory.FASHION.value, []),
    (ProductCategory.FASHION.value, [ReturnFlag.FINAL_SALE.value]),
    (ProductCategory.ELECTRONICS.value, []),
    (ProductCategory.COSMETICS.value, [ReturnFlag.SEALED_COSMETIC.value]),
    (ProductCategory.UNDERGARMENTS.value, [ReturnFlag.HYGIENE.value]),
    (ProductCategory.ACCESSORIES.value, []),
    (ProductCategory.FOOD_PERISHABLE.value, [ReturnFlag.PERISHABLE.value]),
]

ORDER_STATUS_LIST = [
    "pending_payment",
    "confirmed",
    "packing",
    "shipped",
    "out_for_delivery",
    "delivered",
    "delivered",
    "delivered",
    "completed",
    "cancelled",
]

PRODUCT_NAMES = {
    "fashion": ["Áo sơ mi linen", "Quần jeans ống suông", "Váy midi hoa nhí", "Áo hoodie nỉ", "Giày sneaker trắng", "Áo polo pique", "Quần short kaki"],
    "electronics_accessories": ["Tai nghe không dây", "Sạc nhanh 65W", "Ốp lưng chống sốc", "Chuột không dây", "Cáp USB-C bện dù", "Loa Bluetooth mini"],
    "cosmetics": ["Kem chống nắng SPF50", "Sữa rửa mặt dịu nhẹ", "Serum vitamin C", "Son dưỡng có màu", "Mặt nạ cấp ẩm"],
    "home_living": ["Bình giữ nhiệt 500ml", "Bộ ga giường cotton", "Hộp đựng thực phẩm", "Đèn ngủ để bàn", "Khăn tắm bông"],
}

PAYMENT_METHODS = [
    PaymentMethod.CARD.value,
    PaymentMethod.EWALLET.value,
    PaymentMethod.BANK_TRANSFER.value,
    PaymentMethod.COD.value,
]


async def generate_seed_data(
    session: AsyncSession,
    seed: int = 20261111,
    now: datetime | None = None,
    num_customers: int = 300,
    num_products: int = 120,
    num_orders: int = 1500,
) -> dict[str, int]:
    """Populate database with deterministic realistic dataset."""
    rng = random.Random(seed)
    if now is None:
        now = datetime(2026, 11, 11, 9, 0, 0)

    # 1. Staff users
    staff_users = [
        StaffUserModel(
            id=uuid.UUID(int=1),
            email="agent@shop.vn",
            password_hash=hash_password("staff123"),
            role="agent",
            full_name="Nguyễn Văn Nhân Viên",
            created_at=now - timedelta(days=60),
        ),
        StaffUserModel(
            id=uuid.UUID(int=2),
            email="supervisor@shop.vn",
            password_hash=hash_password("staff123"),
            role="supervisor",
            full_name="Trần Thị Trưởng Ca",
            created_at=now - timedelta(days=60),
        ),
        StaffUserModel(
            id=uuid.UUID(int=3),
            email="admin@shop.vn",
            password_hash=hash_password("admin123"),
            role="admin",
            full_name="Lê Quản Trị",
            created_at=now - timedelta(days=60),
        ),
    ]
    session.add_all(staff_users)
    await session.flush()

    # 2. Customers & Credentials
    customers: list[CustomerModel] = []
    pwd_hash = hash_password("pass123")
    for i in range(1, num_customers + 1):
        cust_id = uuid.UUID(int=1000 + i)
        tier = "diamond" if i <= 15 else ("gold" if i <= 60 else ("silver" if i <= 150 else "standard"))
        created_days_ago = rng.randint(10, 365)
        cust = CustomerModel(
            id=cust_id,
            email=f"customer{i}@example.com",
            phone=f"09{i:08d}",
            full_name=f"Khách Hàng {i}",
            tier=tier,
            created_at=now - timedelta(days=created_days_ago),
        )
        customers.append(cust)
        cred = CustomerCredentialsModel(
            customer_id=cust_id,
            password_hash=pwd_hash,
            created_at=cust.created_at,
        )
        cust.credentials = cred
        session.add(cust)
    await session.flush()

    # 3. Products & Variants (120 products, ~400 variants)
    variants: list[ProductVariantModel] = []
    variant_counter = 1
    for p_idx in range(1, num_products + 1):
        cat, flags = CATEGORIES[p_idx % len(CATEGORIES)]
        prod = ProductModel(
            id=uuid.UUID(int=10000 + p_idx),
            name=f"{rng.choice(PRODUCT_NAMES.get(cat, ['Sản phẩm']))} #{p_idx}",
            category=cat,
            return_flags=flags,
            created_at=now - timedelta(days=120),
        )
        session.add(prod)

        num_vars = rng.randint(2, 5)
        for v_idx in range(1, num_vars + 1):
            price = rng.choice([99000, 149000, 249000, 399000, 599000, 899000, 1290000])
            var = ProductVariantModel(
                id=uuid.UUID(int=100000 + variant_counter),
                product_id=prod.id,
                sku=f"SKU-{cat[:3].upper()}-{p_idx:03d}-{v_idx}",
                attributes={"size": rng.choice(["S", "M", "L", "XL"]), "color": rng.choice(["Đen", "Trắng", "Xanh"])},
                price=price,
                stock=rng.randint(20, 200),
            )
            variants.append(var)
            session.add(var)
            variant_counter += 1
    await session.flush()

    # 4. Orders & Items
    orders: list[OrderModel] = []
    returnable_orders: list[OrderModel] = []
    for o_idx in range(1, num_orders + 1):
        cust = customers[o_idx % len(customers)]
        status = rng.choice(ORDER_STATUS_LIST)
        method = rng.choice(PAYMENT_METHODS)

        # Timestamps relative to now
        if status in ("pending_payment", "confirmed"):
            placed_days_ago = rng.uniform(0.1, 1.5)
            delivered_at = None
        elif status == "packing":
            placed_days_ago = rng.uniform(0.5, 2.0)
            delivered_at = None
        elif status in ("shipped", "out_for_delivery"):
            placed_days_ago = rng.uniform(1.0, 3.5)
            delivered_at = None
        elif status == "cancelled":
            placed_days_ago = rng.uniform(1.0, 20.0)
            delivered_at = None
        else:  # Delivered or return states
            # Stratified delivered days to cover day 2, day 6, day 14, day 16, day 30
            sample_bracket = rng.choice(["recent_3d", "week_1", "week_2", "past_window", "old"])
            if sample_bracket == "recent_3d":
                del_days = rng.uniform(0.5, 3.0)
            elif sample_bracket == "week_1":
                del_days = rng.uniform(3.5, 6.8)
            elif sample_bracket == "week_2":
                del_days = rng.uniform(7.5, 14.5)
            elif sample_bracket == "past_window":
                del_days = rng.uniform(15.5, 20.0)
            else:
                del_days = rng.uniform(21.0, 60.0)

            placed_days_ago = del_days + rng.uniform(2.0, 4.0)
            delivered_at = now - timedelta(days=del_days)

        placed_at = now - timedelta(days=placed_days_ago)

        # Select 1 to 4 items
        item_count = rng.randint(1, 3)
        selected_vars = [rng.choice(variants) for _ in range(item_count)]
        qtys = [rng.randint(1, 2) for _ in range(item_count)]

        subtotal = sum(v.price * q for v, q in zip(selected_vars, qtys, strict=False))
        discount_total = rng.choice([0, 20000, 50000]) if subtotal > 200000 else 0
        shipping_fee = 0 if subtotal >= 500000 else 30000
        total = subtotal - discount_total + shipping_fee

        # Compute allocated discounts ensuring exact equality: sum == discount_total
        items_dict = [{"unit_price": v.price, "qty": q} for v, q in zip(selected_vars, qtys, strict=False)]
        allocated = calculate_allocated_discounts(items_dict, discount_total)

        # Payment status
        if status == "pending_payment":
            p_status = PaymentStatus.UNPAID.value
            paid_amount = 0
        elif status == "cancelled":
            p_status = PaymentStatus.REFUNDED.value if method != PaymentMethod.COD.value else PaymentStatus.UNPAID.value
            paid_amount = 0
        else:
            p_status = PaymentStatus.PAID.value
            paid_amount = total

        order_id = uuid.UUID(int=1000000 + o_idx)
        order = OrderModel(
            id=order_id,
            code=f"SL-{o_idx:06d}",
            customer_id=cust.id,
            status=status,
            payment_method=method,
            payment_status=p_status,
            subtotal=subtotal,
            discount_total=discount_total,
            shipping_fee=shipping_fee,
            total=total,
            paid_amount=paid_amount,
            refunded_amount=0,
            channel="web",
            policy_version="2026-11-01",
            placed_at=placed_at,
            delivered_at=delivered_at,
            created_at=placed_at,
            updated_at=placed_at,
        )
        orders.append(order)
        session.add(order)

        for v, q, alloc in zip(selected_vars, qtys, allocated, strict=False):
            it = OrderItemModel(
                id=generate_uuid(),
                order_id=order.id,
                variant_id=v.id,
                qty=q,
                unit_price=v.price,
                allocated_discount=alloc,
                returned_qty=0,
                exchanged=False,
            )
            session.add(it)

        if p_status in (PaymentStatus.PAID.value, PaymentStatus.REFUNDED.value) and method != PaymentMethod.COD.value:
            session.add(
                PaymentModel(
                    id=generate_uuid(), order_id=order.id, gateway=method, gateway_txn_id=f"SEED-TXN-{o_idx:06d}",
                    amount=total, status="succeeded", mode="simulated", created_at=placed_at,
                )
            )

        ship_events: list[tuple[str, str, datetime]] = []
        if status in ("shipped", "out_for_delivery") or delivered_at is not None:
            start = placed_at + timedelta(days=1)
            ship_events.append(("shipped", "Kho ShopLab, Quận 7, TP.HCM", start))
            ship_events.append(("in_transit", "Trung tâm khai thác", start + timedelta(days=1)))
            if status == "out_for_delivery":
                ship_events.append(("out_for_delivery", "Bưu cục địa phương", now - timedelta(hours=3)))
            if delivered_at is not None:
                ship_events.append(("delivered", "Giao thành công cho người nhận", delivered_at))
        if ship_events:
            ship = ShipmentModel(
                id=generate_uuid(), order_id=order.id, carrier="ShopLab Logistics", tracking_code=f"SLB{o_idx:06d}VN",
                status=ship_events[-1][0], direction="outbound", created_at=ship_events[0][2],
            )
            session.add(ship)
            for st, loc, at in ship_events:
                session.add(ShipmentEventModel(id=generate_uuid(), shipment_id=ship.id, status=st, location=loc, occurred_at=at))

        if delivered_at is not None:
            returnable_orders.append(order)

    await session.flush()

    # 5. Historical return requests (~150): items, evidence, and a refund where one was accepted.
    # Demo customers 1-3 are skipped so their curated history stays exactly as designed.
    demo_ids = {uuid.UUID(int=1000 + n) for n in (1, 2, 3)}
    pool = [o for o in returnable_orders if o.customer_id not in demo_ids]
    order_items = (await session.execute(select(OrderItemModel))).scalars().all()
    items_by_order: dict[uuid.UUID, list[OrderItemModel]] = {}
    for it in order_items:
        items_by_order.setdefault(it.order_id, []).append(it)

    return_count = 0
    used: set[uuid.UUID] = set()
    for ret_idx in range(1, 151):
        if not pool:
            break
        order = pool[(ret_idx * 7) % len(pool)]
        if order.id in used:
            continue
        used.add(order.id)
        ret_status = rng.choice([
            ReturnStatus.COMPLETED.value,
            ReturnStatus.AWAITING_RETURN.value,
            ReturnStatus.RECEIVED.value,
            ReturnStatus.REJECTED.value,
        ])
        reason = rng.choice([
            ReturnReason.DEFECTIVE.value, ReturnReason.CHANGE_OF_MIND.value,
            ReturnReason.DAMAGED_IN_TRANSIT.value, ReturnReason.WRONG_ITEM.value, ReturnReason.NOT_AS_DESCRIBED.value,
        ])
        created = (order.delivered_at or order.placed_at) + timedelta(days=rng.uniform(0.5, 4.0))
        if created > now:
            created = now - timedelta(hours=1)
        ret_id = uuid.UUID(int=2000000 + ret_idx)
        session.add(
            ReturnRequestModel(
                id=ret_id, code=f"RT-{ret_idx:06d}", order_id=order.id, customer_id=order.customer_id,
                reason_code=reason, resolution=ReturnResolution.REFUND.value, status=ret_status, risk_flags=[],
                policy_version=order.policy_version,
                deadline_ship_back=created + timedelta(days=5) if ret_status == ReturnStatus.AWAITING_RETURN.value else None,
                created_at=created, updated_at=created,
            )
        )
        net = 0
        for it in items_by_order.get(order.id, []):
            session.add(
                ReturnItemModel(
                    id=generate_uuid(), return_id=ret_id, order_item_id=it.id, qty=it.qty,
                    inspection_result="accepted" if ret_status == ReturnStatus.COMPLETED.value else "pending",
                )
            )
            if ret_status != ReturnStatus.REJECTED.value:
                it.returned_qty = it.qty
            net += it.unit_price * it.qty - it.allocated_discount
        if reason != ReturnReason.CHANGE_OF_MIND.value:
            for p in range(1, 3):
                path = f"seed/RT-{ret_idx:06d}/photo-{p}.jpg"
                session.add(
                    EvidenceFileModel(
                        id=generate_uuid(), return_id=ret_id, kind="photo", path=path,
                        sha256=hashlib.sha256(path.encode()).hexdigest(), size=150_000, uploaded_by="customer", created_at=created,
                    )
                )
        if ret_status == ReturnStatus.COMPLETED.value and net > 0:
            session.add(
                RefundModel(
                    id=generate_uuid(), code=f"RF-{ret_idx:06d}", order_id=order.id, return_id=ret_id, amount=net,
                    breakdown={"net_refundable": net}, method="original", status="succeeded",
                    gateway_txn_id=f"SEED-RFD-{ret_idx:06d}", attempts=1, created_at=created, updated_at=created,
                )
            )
            order.refunded_amount = net
            order.payment_status = PaymentStatus.REFUNDED.value if net >= order.paid_amount else PaymentStatus.PARTIALLY_REFUNDED.value
        return_count += 1

    await session.flush()
    demo = await seed_demo_scenarios(session, now)

    await session.commit()

    return {
        "staff": len(staff_users),
        "customers": len(customers),
        "products": num_products,
        "variants": len(variants),
        "orders": len(orders),
        "returns": return_count,
        **demo,
    }
