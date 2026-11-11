"""FastAPI dependency injection utilities."""

from __future__ import annotations

from typing import AsyncGenerator
import uuid
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.errors import AppError, AuthenticationError, ForbiddenError
from shopagent.core.principal import Principal, PrincipalRole
from shopagent.core.security import decode_access_token
from shopagent.infra.db.session import async_session_factory

security = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide transactional async session per request."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    query_guest_token: str | None = Query(default=None, alias="guest_token"),
    query_token: str | None = Query(default=None, alias="token"),
) -> Principal:
    """Extract authenticated Principal from Bearer JWT, Query Token, or Guest Token."""
    raw_token = (creds.credentials if creds else None) or query_token
    if raw_token:
        try:
            payload = decode_access_token(raw_token)
            role_str = payload.get("role", "customer")
            sub = payload.get("sub")
            if role_str in ("agent", "supervisor", "admin"):
                return Principal.staff(
                    staff_id=uuid.UUID(sub),
                    role=PrincipalRole(role_str),
                    email=payload.get("email", ""),
                )
            elif role_str == "guest":
                verified_oid = payload.get("verified_order_id")
                order_uuid = uuid.UUID(verified_oid) if verified_oid else None
                return Principal.guest(guest_token=raw_token, verified_order_id=order_uuid)
            elif role_str == "customer":
                return Principal.customer(
                    customer_id=uuid.UUID(sub),
                    email=payload.get("email", ""),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Vai trò trong token không hợp lệ.",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ hoặc đã hết hạn.",
            )

    # Guest session fallback (header or query)
    effective_guest_token = guest_token or query_guest_token
    if effective_guest_token:
        try:
            payload = decode_access_token(effective_guest_token)
            verified_oid = payload.get("verified_order_id")
            order_uuid = uuid.UUID(verified_oid) if verified_oid else None
            return Principal.guest(guest_token=effective_guest_token, verified_order_id=order_uuid)
        except Exception:
            return Principal.guest(guest_token=effective_guest_token)

    return Principal.guest()


def require_authenticated(principal: Principal = Depends(get_current_principal)) -> Principal:
    """Ensure principal is logged in (customer or staff)."""
    if principal.is_guest:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu đăng nhập để thực hiện thao tác này.",
        )
    return principal


def require_staff_role(allowed_roles: list[str]):
    """Ensure principal is a staff member with required role."""
    def _role_checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.is_staff or principal.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này.",
            )
        return principal
    return _role_checker
