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
    except AppError:
        await session.rollback()
        raise  # the app-wide handler answers with the error's own status and code


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
    except AppError:
        await session.rollback()
        raise  # the app-wide handler answers with the error's own status and code


_EVIDENCE_TYPES = {
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".webp": "photo",
    ".mp4": "video",
}
_MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
_MAX_EVIDENCE_FILES = 6


@router.post("/returns/{code}/evidence")
async def upload_evidence_file(
    code: str,
    files: list[UploadFile] = File(...),
    principal: Principal = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload photo/video evidence (JPG, PNG, WEBP, MP4; up to 10 MB each) for a return request."""
    ret = (await session.execute(select(ReturnRequestModel).where(ReturnRequestModel.code == code.upper()))).scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu đổi trả.")
    if ret.customer_id != principal.customer_id and not principal.is_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền tải lên bằng chứng cho yêu cầu này.")
    if len(files) > _MAX_EVIDENCE_FILES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Tối đa {_MAX_EVIDENCE_FILES} tệp mỗi lần tải lên.")

    # Validate every file before writing any of them, so a bad file does not leave a partial upload.
    accepted: list[tuple[str, str, bytes]] = []
    for upload in files:
        ext = Path(upload.filename or "").suffix.lower()
        kind = _EVIDENCE_TYPES.get(ext)
        if kind is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Định dạng {ext or 'không rõ'} không được hỗ trợ (JPG, PNG, WEBP, MP4).")
        content = await upload.read()
        if len(content) > _MAX_EVIDENCE_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Tệp {upload.filename} vượt quá 10MB.")
        accepted.append((ext, kind, content))

    saved: list[dict[str, str]] = []
    for ext, kind, content in accepted:
        file_hash = hashlib.sha256(content).hexdigest()
        file_path = _UPLOAD_DIR / f"{file_hash}{ext}"
        file_path.write_bytes(content)
        evidence = EvidenceFileModel(
            id=uuid.uuid4(),
            return_id=ret.id,
            kind=kind,
            path=str(file_path),
            sha256=file_hash,
            size=len(content),
            uploaded_by="staff" if principal.is_staff else "customer",
        )
        session.add(evidence)
        saved.append({"evidence_id": str(evidence.id), "kind": kind, "sha256": file_hash})
    await session.commit()
    return {"status": "uploaded", "uploaded_count": len(saved), "files": saved}
