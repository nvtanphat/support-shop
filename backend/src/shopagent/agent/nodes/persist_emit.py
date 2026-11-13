"""Node 5: persist_emit - Persist messages and events, emit completion to client."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.state import AgentState
from shopagent.infra.db.tables import (
    AuditLogModel,
    ConversationEventModel,
    ConversationModel,
    IdempotencyKeyModel,
    MessageModel,
)

logger = logging.getLogger(__name__)


async def persist_emit_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Persist conversation messages, citations, and events to DB with turn idempotency."""
    session = config.get("configurable", {}).get("session")
    if session is not None and not isinstance(session, AsyncSession):
        session = None

    verified_output = state.get("verified_output") or ""
    conv_id_str = state.get("conversation_id")
    turn_id = state.get("turn_id") or state.get("request_id")

    if session and conv_id_str:
        try:
            c_uuid = uuid.UUID(conv_id_str)
            # Fetch and lock conversation row for update to guarantee multi-process sequence safety
            stmt_conv = (
                select(ConversationModel)
                .where(ConversationModel.id == c_uuid)
                .with_for_update()
            )
            res_conv = await session.execute(stmt_conv)
            conv = res_conv.scalar_one_or_none()
            if not conv:
                principal_obj = state.get("principal")
                cust_id = principal_obj.customer_id if principal_obj else None
                conv = ConversationModel(
                    id=c_uuid,
                    customer_id=cust_id,
                    mode="ai",
                    last_event_seq=0,
                    last_message_seq=0,
                )
                session.add(conv)
                await session.flush()

            messages = state.get("messages", [])
            latest_human_msg: HumanMessage | None = None
            if messages:
                for m in reversed(messages):
                    if isinstance(m, HumanMessage):
                        latest_human_msg = m
                        break

            human_msg_id = getattr(latest_human_msg, "id", None) if latest_human_msg else None
            effective_turn_key = turn_id or (f"msg_{human_msg_id}" if human_msg_id else None)

            # Check if this exact turn was already persisted
            already_persisted = False
            idemp_key_str = f"turn:{c_uuid}:{effective_turn_key}" if effective_turn_key else None
            if idemp_key_str:
                stmt_idemp = select(IdempotencyKeyModel).where(IdempotencyKeyModel.key == idemp_key_str)
                res_idemp = await session.execute(stmt_idemp)
                if res_idemp.scalar_one_or_none() is not None:
                    already_persisted = True

            if not already_persisted and effective_turn_key:
                stmt_check_ev = (
                    select(ConversationEventModel)
                    .where(
                        ConversationEventModel.conversation_id == c_uuid,
                        ConversationEventModel.type == "message.completed",
                    )
                    .order_by(ConversationEventModel.seq.desc())
                )
                res_check_ev = await session.execute(stmt_check_ev)
                for ev in res_check_ev.scalars().all():
                    pl = ev.payload or {}
                    if pl.get("turn_id") == effective_turn_key or (
                        human_msg_id and pl.get("user_message_id") == human_msg_id
                    ):
                        already_persisted = True
                        break

            # If no turn key was provided, fall back to checking if the latest assistant message was already saved
            if not effective_turn_key and not already_persisted:
                stmt_last_asst = (
                    select(MessageModel)
                    .where(MessageModel.conversation_id == c_uuid, MessageModel.role == "assistant")
                    .order_by(MessageModel.seq.desc())
                    .limit(1)
                )
                last_asst_msg = (await session.execute(stmt_last_asst)).scalar_one_or_none()
                if last_asst_msg and last_asst_msg.content == verified_output.strip():
                    already_persisted = True

            if not already_persisted:
                # Save user message
                if latest_human_msg:
                    user_content = str(latest_human_msg.content).strip()
                    conv.last_message_seq += 1
                    u_msg = MessageModel(
                        conversation_id=c_uuid,
                        seq=conv.last_message_seq,
                        role="customer",
                        content=user_content,
                    )
                    session.add(u_msg)

                # Save assistant verified response
                if verified_output:
                    clean_verified = verified_output.strip()
                    conv.last_message_seq += 1
                    a_msg = MessageModel(
                        conversation_id=c_uuid,
                        seq=conv.last_message_seq,
                        role="assistant",
                        content=clean_verified,
                        citations=list(state.get("retrieved_clauses", [])),
                    )
                    session.add(a_msg)
                    if state.get("error"):  # keep why a reply was replaced, so a blocked answer can be diagnosed later
                        session.add(
                            AuditLogModel(
                                actor_type="agent",
                                actor_id="verify_output",
                                action="turn.blocked",
                                subject_type="conversation",
                                subject_id=str(c_uuid),
                                after_state={"reason": str(state["error"])[:1500], "turn_status": state.get("turn_status")},
                            )
                        )

                    # Persist message.completed event for SSE replay & turn idempotency
                    conv.last_event_seq += 1
                    ev_msg = ConversationEventModel(
                        conversation_id=c_uuid,
                        seq=conv.last_event_seq,
                        type="message.completed",
                        payload={
                            "id": str(a_msg.id),
                            "turn_id": effective_turn_key,
                            "user_message_id": human_msg_id,
                            "seq": conv.last_message_seq,
                            "role": "assistant",
                            "content": clean_verified,
                            "citations": list(state.get("retrieved_clauses", [])),
                            # Which tool backed each numeric/order claim, for auditing a wrong answer.
                            "claim_evidence": dict(state.get("claim_evidence") or {}),
                        },
                    )
                    session.add(ev_msg)

                # Save turn idempotency key
                if idemp_key_str:
                    idemp_rec = IdempotencyKeyModel(
                        key=idemp_key_str,
                        scope="turn",
                        response_digest={
                            "verified_output": verified_output.strip() if verified_output else "",
                            "citations": list(state.get("retrieved_clauses", [])),
                        },
                    )
                    session.add(idemp_rec)

            # Persist pending action event if any and not already emitted
            pending_action = state.get("pending_action")
            if pending_action:
                act_id_val = str(pending_action.get("action_id") or pending_action.get("id"))
                stmt_ev_check = (
                    select(ConversationEventModel)
                    .where(
                        ConversationEventModel.conversation_id == c_uuid,
                        ConversationEventModel.type == "action.proposed",
                    )
                    .order_by(ConversationEventModel.seq.desc())
                )
                ev_rows = (await session.execute(stmt_ev_check)).scalars().all()
                already_emitted = any(
                    (ev.payload or {}).get("action_id") == act_id_val
                    or (ev.payload or {}).get("id") == act_id_val
                    for ev in ev_rows
                )

                if not already_emitted:
                    conv.last_event_seq += 1
                    ev_act = ConversationEventModel(
                        conversation_id=c_uuid,
                        seq=conv.last_event_seq,
                        type="action.proposed",
                        payload=pending_action,
                    )
                    session.add(ev_act)

            await session.flush()
        except Exception as e:
            logger.error("Failed to persist turn: %s", e, exc_info=True)
            raise

    update: dict[str, Any] = {"verified_output": verified_output}
    history_message = _history_message_for(state.get("messages", []), verified_output)
    if history_message is not None:
        update["messages"] = [history_message]
    return update


def _history_message_for(messages: list[BaseMessage], verified_output: str) -> AIMessage | None:
    """Return the message that makes the conversation history match what the customer saw.

    A completed turn ends with a final AIMessage: replace it (same id) when verification changed
    its text. Any other ending (deflection, degraded turn, unmet requirement) has no customer-facing
    assistant message yet, so one is appended.
    """
    if not verified_output:
        return None
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and not last.tool_calls:
        if last.content == verified_output:
            return None
        return AIMessage(content=verified_output, id=last.id)
    return AIMessage(content=verified_output, id=f"ai-{uuid.uuid4()}")
