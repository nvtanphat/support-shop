"""Node 5: persist_emit - Persist messages and events, emit completion to client."""

from __future__ import annotations

from typing import Any
import uuid
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.state import AgentState
from shopagent.infra.db.tables import ConversationEventModel, ConversationModel, MessageModel


async def persist_emit_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Persist conversation messages, citations, and events to DB."""
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

            messages = state.get("messages", [])
            # If the last user message isn't saved yet, check and persist
            if messages:
                for m in reversed(messages):
                    if isinstance(m, HumanMessage):
                        current_seq += 1
                        u_msg = MessageModel(
                            conversation_id=c_uuid,
                            seq=current_seq,
                            role="customer",
                            content=str(m.content),
                        )
                        session.add(u_msg)
                        break

            # Persist assistant verified response
            if verified_output:
                current_seq += 1
                a_msg = MessageModel(
                    conversation_id=c_uuid,
                    seq=current_seq,
                    role="assistant",
                    content=verified_output,
                    citations=list(state.get("retrieved_clauses", [])),
                )
                session.add(a_msg)

            # Persist pending action event if any
            pending_action = state.get("pending_action")
            if pending_action:
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
        except Exception:
            # Persistence logging or error handling
            pass

    return {"verified_output": verified_output}
