"""Actions confirmation, cancellation, and evidence upload router."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session, require_authenticated
from shopagent.api.schemas.models import CancelActionRequest, ConfirmActionRequest
from shopagent.core.config import PROJECT_ROOT
from shopagent.core.errors import AppError
from shopagent.core.principal import Principal
from shopagent.domain.services.actions import ActionService
from shopagent.infra.db.tables import EvidenceFileModel, ReturnRequestModel

router = APIRouter(tags=["Actions"])

_UPLOAD_DIR = PROJECT_ROOT / "backend" / "data" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/actions/{action_id}/confirm")
async def confirm_action(
    action_id: uuid.UUID,
    req: ConfirmActionRequest,
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """Customer confirms proposed action by clicking action card button."""
    service = ActionService(session)
    try:
        result = await service.confirm_action(
            principal=principal,
            action_id=action_id,
            preview_hash=req.preview_hash,
        )
        await session.commit()
        return result
    except AppError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": e.error_code, "message": str(e)},
        ) from e


@router.post("/actions/{action_id}/cancel")
async def cancel_action(
    action_id: uuid.UUID,
    req: CancelActionRequest,
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """Customer explicitly cancels proposed action."""
    service = ActionService(session)
    try:
        result = await service.cancel_action(
            principal=principal,
            action_id=action_id,
            reason=req.reason,
        )
        await session.commit()
        return result
    except AppError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": e.error_code, "message": str(e)},
        ) from e


@router.post("/returns/{code}/evidence")
async def upload_evidence_file(
    code: str,
    file: UploadFile = File(...),
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload photo/video evidence for return request."""
    stmt = select(ReturnRequestModel).where(ReturnRequestModel.code == code.upper())
    res = await session.execute(stmt)
    ret = res.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu đổi trả.")

    if ret.customer_id != principal.customer_id and not principal.is_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền tải lên bằng chứng cho yêu cầu này.")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Tệp tin vượt quá 20MB.")

    file_hash = hashlib.sha256(content).hexdigest()
    ext = Path(file.filename or "evidence.jpg").suffix
    file_path = _UPLOAD_DIR / f"{file_hash}{ext}"
    file_path.write_bytes(content)

    kind = "video" if ext.lower() in (".mp4", ".mov", ".mkv", ".webm") else "photo"

    ev = EvidenceFileModel(
        id=uuid.uuid4(),
        return_id=ret.id,
        kind=kind,
        path=str(file_path),
        sha256=file_hash,
        size=len(content),
        uploaded_by="customer",
    )
    session.add(ev)
    await session.commit()

    return {
        "status": "uploaded",
        "evidence_id": str(ev.id),
        "kind": kind,
        "sha256": file_hash,
    }
