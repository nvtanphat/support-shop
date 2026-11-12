"""Node 5: persist_emit - Persist messages and events, emit completion to client."""

from __future__ import annotations

import logging
from typing import Any
import uuid
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.state import AgentState
from shopagent.infra.db.tables import ConversationEventModel, ConversationModel, MessageModel

logger = logging.getLogger(__name__)


async def persist_emit_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Persist conversation messages, citations, and events to DB without duplication."""
    session: AsyncSession = config.get("configurable", {}).get("session")

    verified_output = state.get("verified_output") or ""
    conv_id_str = state.get("conversation_id")

    if session and conv_id_str:
        try:
            c_uuid = uuid.UUID(conv_id_str)
            # Ensure conversation exists
            stmt_conv = select(ConversationModel).where(ConversationModel.id == c_uuid)
            res_conv = await session.execute(stmt_conv)
            conv = res_conv.scalar_one_or_none()
            if not conv:
                conv = ConversationModel(
                    id=c_uuid,
                    customer_id=state.get("principal").customer_id if state.get("principal") else None,
                    mode="ai",
                )
                session.add(conv)
                await session.flush()

            # Get current max sequence number for messages
            stmt_seq = select(func.coalesce(func.max(MessageModel.seq), 0)).where(
                MessageModel.conversation_id == c_uuid
            )
            res_seq = await session.execute(stmt_seq)
            current_seq = res_seq.scalar_one()

            # Find the latest saved customer and assistant messages in DB to prevent duplicates on retries
            stmt_last_cust = (
                select(MessageModel)
                .where(MessageModel.conversation_id == c_uuid, MessageModel.role == "customer")
                .order_by(MessageModel.seq.desc())
                .limit(1)
            )
            last_cust_msg = (await session.execute(stmt_last_cust)).scalar_one_or_none()

            stmt_last_asst = (
                select(MessageModel)
                .where(MessageModel.conversation_id == c_uuid, MessageModel.role == "assistant")
                .order_by(MessageModel.seq.desc())
                .limit(1)
            )
            last_asst_msg = (await session.execute(stmt_last_asst)).scalar_one_or_none()

            # Check and persist the user's latest HumanMessage if not already saved
            messages = state.get("messages", [])
            latest_human_msg: HumanMessage | None = None
            if messages:
                for m in reversed(messages):
                    if isinstance(m, HumanMessage):
                        latest_human_msg = m
                        break

            if latest_human_msg:
                user_content = str(latest_human_msg.content).strip()
                if not (last_cust_msg and last_cust_msg.content == user_content):
                    current_seq += 1
                    u_msg = MessageModel(
                        conversation_id=c_uuid,
                        seq=current_seq,
                        role="customer",
                        content=user_content,
                    )
                    session.add(u_msg)

            # Persist assistant verified response if not already saved
            if verified_output:
                clean_verified = verified_output.strip()
                if not (last_asst_msg and last_asst_msg.content == clean_verified):
                    current_seq += 1
                    a_msg = MessageModel(
                        conversation_id=c_uuid,
                        seq=current_seq,
                        role="assistant",
                        content=clean_verified,
                        citations=list(state.get("retrieved_clauses", [])),
                    )
                    session.add(a_msg)

                    # Persist message.completed event for SSE replay
                    stmt_ev_seq = select(func.coalesce(func.max(ConversationEventModel.seq), 0)).where(
                        ConversationEventModel.conversation_id == c_uuid
                    )
                    res_ev_seq = await session.execute(stmt_ev_seq)
                    ev_seq = res_ev_seq.scalar_one() + 1
                    ev_msg = ConversationEventModel(
                        conversation_id=c_uuid,
                        seq=ev_seq,
                        type="message.completed",
                        payload={
                            "id": str(a_msg.id),
                            "seq": current_seq,
                            "role": "assistant",
                            "content": clean_verified,
                            "citations": list(state.get("retrieved_clauses", [])),
                        },
                    )
                    session.add(ev_msg)

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
                    .limit(5)
                )
                ev_rows = (await session.execute(stmt_ev_check)).scalars().all()
                already_emitted = any(
                    (ev.payload or {}).get("action_id") == act_id_val
                    or (ev.payload or {}).get("id") == act_id_val
                    for ev in ev_rows
                )

                if not already_emitted:
                    stmt_ev_seq = select(func.coalesce(func.max(ConversationEventModel.seq), 0)).where(
                        ConversationEventModel.conversation_id == c_uuid
                    )
                    res_ev_seq = await session.execute(stmt_ev_seq)
                    ev_seq = res_ev_seq.scalar_one() + 1

                    ev = ConversationEventModel(
                        conversation_id=c_uuid,
                        seq=ev_seq,
                        type="action.proposed",
                        payload=pending_action,
                    )
                    session.add(ev)

            await session.flush()
        except Exception as e:
            logger.error("Failed to persist turn: %s", e, exc_info=True)
            raise

    return {"verified_output": verified_output}
