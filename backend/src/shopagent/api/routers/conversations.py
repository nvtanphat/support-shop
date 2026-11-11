"""Conversations router handling chat messages and real-time SSE streaming."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from langchain_core.messages import HumanMessage
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.graph import get_agent_graph
from shopagent.agent.state import AgentState
from shopagent.api.deps import get_current_principal, get_db_session
from shopagent.api.schemas.models import (
    ConversationDto,
    CreateConversationRequest,
    MessageDto,
    SendMessageRequest,
)
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal
from shopagent.domain.services.tickets import TicketService
from shopagent.infra.db.tables import ConversationEventModel, ConversationModel, MessageModel

router = APIRouter(tags=["Conversations"])


@router.post("/conversations", response_model=ConversationDto)
async def create_conversation(
    req: CreateConversationRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDto:
    """Create a new chat conversation."""
    conv_id = uuid.uuid4()
    cust_id = principal.customer_id if principal.is_authenticated_customer else None

    conv = ConversationModel(
        id=conv_id,
        customer_id=cust_id,
        mode="ai",
    )
    session.add(conv)
    await session.commit()

    return ConversationDto(
        id=str(conv.id),
        customer_id=str(cust_id) if cust_id else None,
        channel=req.channel,
        mode=conv.mode,
        created_at=conv.created_at.isoformat(),
        messages=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDto)
async def get_conversation(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDto:
    """Get conversation details and full message history."""
    stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    # Access control
    if principal.is_authenticated_customer and conv.customer_id != principal.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập cuộc trò chuyện này.")

    stmt_msgs = (
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.seq.asc())
    )
    res_msgs = await session.execute(stmt_msgs)
    msgs = res_msgs.scalars().all()

    return ConversationDto(
        id=str(conv.id),
        customer_id=str(conv.customer_id) if conv.customer_id else None,
        channel="web",
        mode=conv.mode,
        created_at=conv.created_at.isoformat(),
        messages=[
            MessageDto(
                id=str(m.id),
                seq=m.seq,
                role=m.role,
                content=m.content,
                citations=m.citations or [],
                created_at=m.created_at.isoformat(),
            )
            for m in msgs
        ],
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    req: SendMessageRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Send customer message and invoke LangGraph Agent pipeline."""
    stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    if principal.is_authenticated_customer and conv.customer_id and conv.customer_id != principal.customer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập cuộc trò chuyện này.")

    # If conversation is with human staff, save user message and do not invoke AI
    if conv.mode in ("waiting_human", "human"):
        stmt_seq = select(func.coalesce(func.max(MessageModel.seq), 0)).where(
            MessageModel.conversation_id == conversation_id
        )
        res_seq = await session.execute(stmt_seq)
        seq = res_seq.scalar_one() + 1
        msg = MessageModel(
            conversation_id=conversation_id,
            seq=seq,
            role="customer",
            content=req.content,
        )
        session.add(msg)
        await session.commit()
        return {
            "status": "waiting_human",
            "message": "Tin nhắn đã được chuyển tới nhân viên chăm sóc khách hàng.",
        }

    # Execute 5-node LangGraph pipeline
    graph = get_agent_graph()
    initial_state: AgentState = {
        "conversation_id": str(conversation_id),
        "messages": [HumanMessage(content=req.content)],
        "principal": principal,
        "clock": get_clock().now(),
    }
    config = {
        "configurable": {
            "thread_id": str(conversation_id),
            "session": session,
        }
    }

    output = await graph.ainvoke(initial_state, config=config)
    await session.commit()

    return {
        "verified_output": output.get("verified_output"),
        "pending_action": output.get("pending_action"),
        "tool_calls": output.get("tool_calls", []),
    }


@router.get("/conversations/{conversation_id}/events")
async def conversation_events_stream(
    conversation_id: uuid.UUID,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    session: AsyncSession = Depends(get_db_session),
):
    """Server-Sent Events (SSE) stream for real-time conversation updates."""
    async def _event_generator() -> AsyncGenerator[dict[str, Any], None]:
        # 1. Replay durable events since last_event_id
        last_seq = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
        stmt = (
            select(ConversationEventModel)
            .where(
                ConversationEventModel.conversation_id == conversation_id,
                ConversationEventModel.seq > last_seq,
            )
            .order_by(ConversationEventModel.seq.asc())
        )
        res = await session.execute(stmt)
        events = res.scalars().all()
        for ev in events:
            yield {
                "event": ev.type,
                "id": str(ev.seq),
                "data": json.dumps(ev.payload, ensure_ascii=False),
            }

        # Keep connection open for brief polling/heartbeat
        yield {"event": "ping", "data": "connected"}

    return EventSourceResponse(_event_generator())


@router.post("/conversations/{conversation_id}/handoff")
async def handoff_to_human(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Customer explicitly clicks button to talk to human staff."""
    stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    conv.mode = "waiting_human"
    ticket_service = TicketService(session)
    ticket = await ticket_service.create_ticket(
        principal=principal,
        conversation_id=conversation_id,
        reason_code="customer_request",
        agent_summary="Khách hàng yêu cầu gặp chuyên viên hỗ trợ trực tiếp.",
        priority="high",
    )
    await session.commit()

    return {
        "status": "waiting_human",
        "ticket_code": ticket.code,
        "message": "Cuộc trò chuyện đã được chuyển tới nhân viên chăm sóc khách hàng.",
    }
