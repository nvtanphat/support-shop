"""Deterministic seed data generator for shop-support-agent.

Generates 300 customers, credentials, staff users, 120 products with 400 variants,
1,500 orders covering all states, and 150 historical return requests.
Deterministic by seed and relative to specified reference timestamp (--now).
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.ids import (
    generate_uuid,
)
from shopagent.core.security import hash_password
from shopagent.domain.models.enums import (
    OrderStatus,
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
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductVariantModel,
    ReturnRequestModel,
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
    OrderStatus.PENDING_PAYMENT.value,
    OrderStatus.PAID.value,
    OrderStatus.PACKING.value,
    OrderStatus.SHIPPED.value,
    OrderStatus.DELIVERED.value,
    OrderStatus.DELIVERED.value,  # Weight delivered heavier for returns
    OrderStatus.DELIVERED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.RETURN_REQUESTED.value,
    OrderStatus.RETURNED.value,
    OrderStatus.PARTIALLY_RETURNED.value,
]

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
            name=f"Sản phẩm {cat.capitalize()} #{p_idx}",
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
        if status in (OrderStatus.PENDING_PAYMENT.value, OrderStatus.PAID.value):
            placed_days_ago = rng.uniform(0.1, 1.5)
            delivered_at = None
        elif status == OrderStatus.PACKING.value:
            placed_days_ago = rng.uniform(0.5, 2.0)
            delivered_at = None
        elif status == OrderStatus.SHIPPED.value:
            placed_days_ago = rng.uniform(1.0, 3.5)
            delivered_at = None
        elif status == OrderStatus.CANCELLED.value:
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
        if status == OrderStatus.PENDING_PAYMENT.value:
            p_status = PaymentStatus.UNPAID.value
            paid_amount = 0
        elif status == OrderStatus.CANCELLED.value:
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

        if delivered_at is not None:
            returnable_orders.append(order)

    await session.flush()

    # 5. Historical Return Requests (~150 returns)
    return_count = 0
    for ret_idx in range(1, 151):
        if not returnable_orders:
            break
        order = returnable_orders[ret_idx % len(returnable_orders)]
        ret_status = rng.choice([
            ReturnStatus.COMPLETED.value,
            ReturnStatus.AWAITING_RETURN.value,
            ReturnStatus.RECEIVED.value,
            ReturnStatus.REJECTED.value,
        ])
        reason = rng.choice([ReturnReason.DEFECTIVE.value, ReturnReason.CHANGE_OF_MIND.value])

        return_req = ReturnRequestModel(
            id=uuid.UUID(int=2000000 + ret_idx),
            code=f"RT-{ret_idx:06d}",
            order_id=order.id,
            customer_id=order.customer_id,
            reason_code=reason,
            resolution=ReturnResolution.REFUND.value,
            status=ret_status,
            risk_flags=[],
            policy_version=order.policy_version,
            deadline_ship_back=now + timedelta(days=5),
            created_at=order.placed_at + timedelta(days=5),
        )
        session.add(return_req)
        return_count += 1

    await session.commit()

    return {
        "staff": len(staff_users),
        "customers": len(customers),
        "products": num_products,
        "variants": len(variants),
        "orders": len(orders),
        "returns": return_count,
    }
