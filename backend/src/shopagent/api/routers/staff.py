"""Internal staff operations router for CSKH agents, supervisors, and admins."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.api.deps import get_db_session, require_staff_role
from shopagent.api.schemas.models import ApprovalDecisionRequest, StaffHandoffMessageRequest
from shopagent.core.principal import Principal
from shopagent.domain.services.approvals import ApprovalService
from shopagent.infra.db.tables import (
    ApprovalRequestModel,
    ConversationModel,
    MessageModel,
    TicketModel,
)

router = APIRouter(prefix="/staff", tags=["Staff Operations"])


@router.get("/approvals")
async def list_approvals(
    status: str = Query(default="pending"),
    gate: str | None = Query(default=None),
    principal: Principal = Depends(require_staff_role(["agent", "supervisor", "admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """List approval queue requests."""
    stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.status == status)
    if gate:
        stmt = stmt.where(ApprovalRequestModel.gate == gate)
    res = await session.execute(stmt)
    approvals = res.scalars().all()
    return {
        "approvals": [
            {
                "id": str(a.id),
                "gate": a.gate,
                "target_type": a.subject_type,
                "target_id": str(a.subject_id),
                "status": a.status,
                "required_role": a.required_role,
                "risk_flags": [],
                "created_at": a.requested_at.isoformat(),
            }
            for a in approvals
        ]
    }


@router.post("/approvals/{approval_id}/decision")
async def make_approval_decision(
    approval_id: uuid.UUID,
    req: ApprovalDecisionRequest,
    principal: Principal = Depends(require_staff_role(["agent", "supervisor", "admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """Staff decides on an approval request."""
    service = ApprovalService(session)
    if req.decision == "approve":
        result_model = await service.decide_approval(principal, approval_id, decision="approved", note=req.note)
    elif req.decision == "reject":
        result_model = await service.decide_approval(principal, approval_id, decision="rejected", note=req.note)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quyết định phải là 'approve' hoặc 'reject'.")

    await session.commit()
    return {"status": result_model.status, "approval_id": str(result_model.id)}


@router.get("/tickets")
async def list_tickets(
    status: str = Query(default="open"),
    principal: Principal = Depends(require_staff_role(["agent", "supervisor", "admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """List open support tickets."""
    stmt = select(TicketModel).where(TicketModel.status == status)
    res = await session.execute(stmt)
    tickets = res.scalars().all()
    return {
        "tickets": [
            {
                "id": str(t.id),
                "code": t.code,
                "conversation_id": str(t.conversation_id),
                "status": t.status,
                "priority": t.priority,
                "reason_code": t.reason_code,
                "summary": t.agent_summary,
                "assigned_to": str(t.assignee) if t.assignee else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in tickets
        ]
    }


@router.post("/tickets/{ticket_id}/claim")
async def claim_ticket(
    ticket_id: uuid.UUID,
    principal: Principal = Depends(require_staff_role(["agent", "supervisor", "admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """Agent claims ticket and takes over conversation."""
    stmt = select(TicketModel).where(TicketModel.id == ticket_id)
    res = await session.execute(stmt)
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu hỗ trợ.")

    ticket.assignee = principal.staff_id
    ticket.status = "in_progress"

    # Set conversation mode to human
    stmt_c = select(ConversationModel).where(ConversationModel.id == ticket.conversation_id)
    res_c = await session.execute(stmt_c)
    conv = res_c.scalar_one_or_none()
    if conv:
        conv.mode = "human"

    await session.commit()
    return {"status": "claimed", "ticket_code": ticket.code}


@router.post("/conversations/{conversation_id}/messages")
async def staff_send_message(
    conversation_id: uuid.UUID,
    req: StaffHandoffMessageRequest,
    principal: Principal = Depends(require_staff_role(["agent", "supervisor", "admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """Staff agent sends message directly to customer in takeover mode."""
    stmt_c = (
        select(ConversationModel)
        .where(ConversationModel.id == conversation_id)
        .with_for_update()
    )
    res_c = await session.execute(stmt_c)
    conv = res_c.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    conv.last_message_seq += 1
    seq = conv.last_message_seq

    msg = MessageModel(
        conversation_id=conversation_id,
        seq=seq,
        role="staff",
        content=req.content,
        author_staff_id=principal.staff_id,
    )
    session.add(msg)
    await session.commit()

    return {"status": "sent", "seq": seq}


@router.post("/conversations/{conversation_id}/return-to-ai")
async def return_conversation_to_ai(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(require_staff_role(["agent", "supervisor", "admin"])),
    session: AsyncSession = Depends(get_db_session),
):
    """Staff agent hands conversation back to AI Assistant."""
    stmt_c = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res_c = await session.execute(stmt_c)
    conv = res_c.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    conv.mode = "ai"
    await session.commit()
    return {"status": "returned_to_ai", "mode": "ai"}
