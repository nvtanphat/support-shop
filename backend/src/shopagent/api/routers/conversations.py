"""Conversations router handling chat messages and real-time SSE streaming."""

from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from shopagent.agent.graph import get_agent_graph
from shopagent.agent.state import AgentState
from shopagent.api.deps import get_current_principal, get_db_session
from shopagent.api.schemas.models import (
    ConversationDto,
    CreateConversationRequest,
    FeedbackRequest,
    MessageDto,
    SendMessageRequest,
)
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal
from shopagent.domain.services.tickets import TicketService
from shopagent.infra.db.tables import (
    AuditLogModel,
    ConversationEventModel,
    ConversationModel,
    IdempotencyKeyModel,
    MessageModel,
    PendingActionModel,
)

router = APIRouter(tags=["Conversations"])

_conv_locks: dict[uuid.UUID, asyncio.Lock] = {}


def _get_conv_lock(conv_id: uuid.UUID) -> asyncio.Lock:
    if conv_id not in _conv_locks:
        _conv_locks[conv_id] = asyncio.Lock()
    return _conv_locks[conv_id]


def verify_conversation_access(
    conv: ConversationModel,
    principal: Principal,
    guest_token: str | None = None,
) -> None:
    """Enforce strict horizontal authorization (IDOR and cross-tenant protection).
    
    Rules:
    1. Staff/Supervisor/Admin has full read/write access.
    2. Authenticated customer can only access conversations where conv.customer_id == principal.customer_id.
    3. Guest can only access guest conversations (conv.customer_id is None).
       The caller MUST provide the valid matching guest_token for that conversation.
    4. Guest CANNOT access conversations owned by an authenticated customer under any circumstances.
    """
    if principal.is_staff:
        return

    # If conversation belongs to an authenticated customer
    if conv.customer_id is not None:
        if not principal.is_authenticated_customer or principal.customer_id != conv.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Không có quyền truy cập cuộc trò chuyện này.",
            )
        return

    # If conversation is a guest conversation (conv.customer_id is None)
    # Both unauthenticated visitors and logged-in customers must provide the matching guest_token to access a guest session
    effective_token = guest_token or principal.guest_token
    if conv.guest_token and (not effective_token or effective_token != conv.guest_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Yêu cầu mã định danh phiên khách vãng lai hợp lệ để truy cập cuộc trò chuyện.",
        )


@router.post("/conversations", response_model=ConversationDto)
async def create_conversation(
    req: CreateConversationRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDto:
    """Create a new chat conversation with secure guest token if unauthenticated."""
    conv_id = uuid.uuid4()
    cust_id = principal.customer_id if principal.is_authenticated_customer else None
    guest_tok = secrets.token_urlsafe(32) if not cust_id else None

    conv = ConversationModel(
        id=conv_id,
        customer_id=cust_id,
        guest_token=guest_tok,
        mode="ai",
    )
    session.add(conv)
    await session.commit()

    return ConversationDto(
        id=str(conv.id),
        conversation_id=str(conv.id),
        customer_id=str(cust_id) if cust_id else None,
        guest_token=guest_tok,
        channel=req.channel,
        mode=conv.mode,
        created_at=conv.created_at.isoformat(),
        messages=[],
        pending_actions=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDto)
async def get_conversation(
    conversation_id: uuid.UUID,
    x_guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    guest_token: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDto:
    """Get conversation details and full message history with strict access check."""
    stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    verify_conversation_access(conv, principal, x_guest_token or guest_token)

    stmt_msgs = (
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.seq.asc())
    )
    res_msgs = await session.execute(stmt_msgs)
    msgs = res_msgs.scalars().all()

    # Active pending actions
    stmt_act = select(PendingActionModel).where(
        PendingActionModel.conversation_id == conversation_id,
        PendingActionModel.status == "proposed",
    )
    res_act = await session.execute(stmt_act)
    acts = res_act.scalars().all()
    now_time = get_clock().now()
    pending_list = [
        {
            "id": str(a.id),
            "action_id": str(a.id),
            "conversation_id": str(a.conversation_id),
            "type": a.type,
            "preview": a.preview,
            "preview_hash": a.payload_hash,
            "status": a.status,
            "expires_at": a.expires_at.isoformat(),
        }
        for a in acts
        if a.expires_at > now_time
    ]

    return ConversationDto(
        id=str(conv.id),
        conversation_id=str(conv.id),
        customer_id=str(conv.customer_id) if conv.customer_id else None,
        guest_token=conv.guest_token,
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
        pending_actions=pending_list,
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    req: SendMessageRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    x_guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    guest_token: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Send customer message and invoke LangGraph Agent pipeline with authorization and turn idempotency."""
    async with _get_conv_lock(conversation_id):
        stmt = (
            select(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .with_for_update()
        )
        res = await session.execute(stmt)
        conv = res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

        verify_conversation_access(conv, principal, x_guest_token or guest_token)

        # Resolve turn idempotency key
        turn_id = x_idempotency_key or req.idempotency_key

        # Check if request was already executed with this idempotency key in IdempotencyKeyModel or events
        if turn_id:
            stmt_idemp = select(IdempotencyKeyModel).where(
                IdempotencyKeyModel.key == f"turn:{conversation_id}:{turn_id}"
            )
            res_idemp = await session.execute(stmt_idemp)
            cached_rec = res_idemp.scalar_one_or_none()
            if cached_rec:
                pl = cached_rec.response_digest
                return {
                    "status": "success",
                    "verified_output": pl.get("verified_output", ""),
                    "assistant_message": pl.get("verified_output", ""),
                    "citations": pl.get("citations", []),
                    "pending_action": pl.get("pending_action"),
                    "tool_calls": [],
                }

            stmt_prior = (
                select(ConversationEventModel)
                .where(
                    ConversationEventModel.conversation_id == conversation_id,
                    ConversationEventModel.type == "message.completed",
                )
                .order_by(ConversationEventModel.seq.desc())
            )
            res_prior = await session.execute(stmt_prior)
            for ev in res_prior.scalars().all():
                pl = ev.payload or {}
                if pl.get("turn_id") == turn_id:
                    return {
                        "status": "success",
                        "verified_output": pl.get("content", ""),
                        "assistant_message": pl.get("content", ""),
                        "citations": pl.get("citations", []),
                        "pending_action": None,
                        "tool_calls": [],
                    }

        # If conversation is with human staff, save user message and do not invoke AI
        if conv.mode in ("waiting_human", "human"):
            conv.last_message_seq += 1
            seq = conv.last_message_seq
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
        effective_turn_id = turn_id or str(uuid.uuid4())
        human_msg_id = str(uuid.uuid4())
        initial_state: AgentState = {
            "conversation_id": str(conversation_id),
            "turn_id": effective_turn_id,
            "request_id": effective_turn_id,
            "messages": [HumanMessage(content=req.content, id=human_msg_id)],
            "principal": principal,
            "clock": get_clock().now(),
        }
        config = {
            "configurable": {
                "thread_id": str(conversation_id),
                "session": session,
            }
        }

        try:
            output = await graph.ainvoke(initial_state, config=config)
            await session.commit()
        except Exception:
            await session.rollback()
            if turn_id:
                stmt_idemp_check = select(IdempotencyKeyModel).where(
                    IdempotencyKeyModel.key == f"turn:{conversation_id}:{turn_id}"
                )
                res_idemp_c = await session.execute(stmt_idemp_check)
                rec_c = res_idemp_c.scalar_one_or_none()
                if rec_c:
                    pl = rec_c.response_digest
                    return {
                        "status": "success",
                        "verified_output": pl.get("verified_output", ""),
                        "assistant_message": pl.get("verified_output", ""),
                        "citations": pl.get("citations", []),
                        "pending_action": pl.get("pending_action"),
                        "tool_calls": [],
                    }
            raise

        verified = output.get("verified_output") or ""
        return {
            "status": "success",
            "verified_output": verified,
            "assistant_message": verified,
            "citations": list(output.get("retrieved_clauses") or []),
            "pending_action": output.get("pending_action"),
            "tool_calls": output.get("tool_calls", []),
        }


@router.get("/conversations/{conversation_id}/events")
async def conversation_events_stream(
    conversation_id: uuid.UUID,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    x_guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    guest_token: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Server-Sent Events (SSE) stream for real-time conversation updates with authorization."""
    stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    verify_conversation_access(conv, principal, x_guest_token or guest_token)

    async def _event_generator() -> AsyncGenerator[dict[str, Any], None]:
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
            if ev.seq > last_seq:
                last_seq = ev.seq
            yield {
                "event": ev.type,
                "id": str(ev.seq),
                "data": json.dumps(ev.payload, ensure_ascii=False),
            }

        yield {"event": "ping", "data": "connected"}

        # Keep connection open for brief heartbeat and event streaming
        for _ in range(60):
            await asyncio.sleep(1.0)
            stmt_new = (
                select(ConversationEventModel)
                .where(
                    ConversationEventModel.conversation_id == conversation_id,
                    ConversationEventModel.seq > last_seq,
                )
                .order_by(ConversationEventModel.seq.asc())
            )
            res_new = await session.execute(stmt_new)
            new_events = res_new.scalars().all()
            for ev in new_events:
                if ev.seq > last_seq:
                    last_seq = ev.seq
                yield {
                    "event": ev.type,
                    "id": str(ev.seq),
                    "data": json.dumps(ev.payload, ensure_ascii=False),
                }

    return EventSourceResponse(_event_generator())


@router.post("/conversations/{conversation_id}/handoff")
async def handoff_to_human(
    conversation_id: uuid.UUID,
    x_guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    guest_token: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Customer explicitly clicks button to talk to human staff."""
    stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")

    verify_conversation_access(conv, principal, x_guest_token or guest_token)

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


@router.post("/conversations/{conversation_id}/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    conversation_id: uuid.UUID,
    req: FeedbackRequest,
    x_guest_token: str | None = Header(default=None, alias="X-Guest-Token"),
    guest_token: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
):
    """Record a satisfaction rating for a conversation in the audit log; every submission is kept."""
    conv = (await session.execute(select(ConversationModel).where(ConversationModel.id == conversation_id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cuộc trò chuyện.")
    verify_conversation_access(conv, principal, x_guest_token or guest_token)

    session.add(
        AuditLogModel(
            actor_type="customer" if principal.is_authenticated_customer else "guest",
            actor_id=str(principal.customer_id or conv.guest_token or "guest"),
            action="conversation.feedback",
            subject_type="conversation",
            subject_id=str(conversation_id),
            after_state={"rating": req.rating, "comment": req.comment},
        )
    )
    await session.commit()
    return {"status": "recorded", "rating": req.rating}
