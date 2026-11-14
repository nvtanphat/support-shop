"""Authentication router for customers and staff."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_current_principal, get_db_session, require_authenticated
from shopagent.api.schemas.models import LoginRequest, StaffLoginRequest, TokenResponse
from shopagent.core.principal import Principal
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


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Issue a fresh access token to a caller whose current token is still valid and whose account still exists."""
    if principal.is_staff:
        staff = await session.get(StaffUserModel, principal.staff_id)
        if staff is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn tồn tại.")
        token = create_access_token(data={"sub": str(staff.id), "email": staff.email, "role": staff.role})
        return TokenResponse(access_token=token, role=staff.role, user_id=str(staff.id), email=staff.email)

    customer = await session.get(CustomerModel, principal.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không còn tồn tại.")
    token = create_access_token(data={"sub": str(customer.id), "email": customer.email, "role": "customer"})
    return TokenResponse(access_token=token, role="customer", user_id=str(customer.id), email=customer.email)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(_principal: Principal = Depends(get_current_principal)) -> None:
    """Tokens are stateless and short-lived; the client discards its token. Nothing is stored server-side."""
