"""Authentication router for customers and staff."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session
from shopagent.api.schemas.models import LoginRequest, StaffLoginRequest, TokenResponse
from shopagent.core.security import create_access_token, verify_password
from shopagent.infra.db.tables import CustomerCredentialsModel, CustomerModel, StaffUserModel

router = APIRouter(tags=["Authentication"])


@router.post("/auth/login", response_model=TokenResponse)
async def customer_login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate customer with email and password."""
    stmt = (
        select(CustomerModel, CustomerCredentialsModel)
        .join(CustomerCredentialsModel, CustomerModel.id == CustomerCredentialsModel.customer_id)
        .where(CustomerModel.email == req.email.lower().strip())
    )
    res = await session.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác.",
        )

    cust, creds = row
    if not verify_password(req.password, creds.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác.",
        )

    token = create_access_token(
        data={"sub": str(cust.id), "email": cust.email, "role": "customer"}
    )
    return TokenResponse(
        access_token=token,
        role="customer",
        user_id=str(cust.id),
        email=cust.email,
    )


@router.post("/staff/auth/login", response_model=TokenResponse)
async def staff_login(
    req: StaffLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate internal staff member."""
    stmt = select(StaffUserModel).where(StaffUserModel.email == req.email.lower().strip())
    res = await session.execute(stmt)
    staff = res.scalar_one_or_none()
    if not staff or not verify_password(req.password, staff.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu nhân viên không chính xác.",
        )

    token = create_access_token(
        data={"sub": str(staff.id), "email": staff.email, "role": staff.role}
    )
    return TokenResponse(
        access_token=token,
        role=staff.role,
        user_id=str(staff.id),
        email=staff.email,
    )
