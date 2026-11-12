"""LangGraph checkpoint persistence on a real PostgreSQL server.

Runs only when TEST_POSTGRES_URL points at a disposable PostgreSQL database; otherwise every
test is reported as skipped (not run), never as passed.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Annotated

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from shopagent.agent.checkpoint import open_postgres_checkpointer
from typing_extensions import TypedDict

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set: PostgreSQL checkpoint tests not run")


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]


def build_graph(saver):  # type: ignore[no-untyped-def]
    def reply(state: ChatState) -> dict:
        return {"messages": [AIMessage(content=f"đã nhận {len(state['messages'])} tin")]}

    builder = StateGraph(ChatState)
    builder.add_node("reply", reply)
    builder.add_edge(START, "reply")
    builder.add_edge("reply", END)
    return builder.compile(checkpointer=saver)


def thread_config() -> dict:
    return {"configurable": {"thread_id": f"t-{uuid.uuid4()}"}}


@pytest.mark.asyncio
async def test_async_graph_persists_and_resumes_on_postgres() -> None:
    handle = await open_postgres_checkpointer(POSTGRES_URL)
    try:
        graph = build_graph(handle.saver)
        cfg = thread_config()
        first = await graph.ainvoke({"messages": [HumanMessage(content="một")]}, cfg)
        second = await graph.ainvoke({"messages": [HumanMessage(content="hai")]}, cfg)
        assert len(first["messages"]) == 2
        assert len(second["messages"]) == 4  # history carried over by the checkpoint
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_state_survives_pool_restart() -> None:
    cfg = thread_config()
    first_handle = await open_postgres_checkpointer(POSTGRES_URL)
    try:
        await build_graph(first_handle.saver).ainvoke({"messages": [HumanMessage(content="trước khi khởi động lại")]}, cfg)
    finally:
        await first_handle.close()

    second_handle = await open_postgres_checkpointer(POSTGRES_URL)  # a new process would do the same
    try:
        snapshot = await build_graph(second_handle.saver).aget_state(cfg)
        contents = [m.content for m in snapshot.values["messages"]]
        assert contents[0] == "trước khi khởi động lại"
        resumed = await build_graph(second_handle.saver).ainvoke({"messages": [HumanMessage(content="sau")]}, cfg)
        assert len(resumed["messages"]) == 4
    finally:
        await second_handle.close()


@pytest.mark.asyncio
async def test_threads_are_isolated_under_concurrency() -> None:
    handle = await open_postgres_checkpointer(POSTGRES_URL)
    try:
        graph = build_graph(handle.saver)
        configs = [thread_config() for _ in range(12)]
        await asyncio.gather(
            *(graph.ainvoke({"messages": [HumanMessage(content=f"khách {i}")]}, cfg) for i, cfg in enumerate(configs))
        )
        for i, cfg in enumerate(configs):
            snapshot = await graph.aget_state(cfg)
            assert [m.content for m in snapshot.values["messages"]][0] == f"khách {i}"
            assert len(snapshot.values["messages"]) == 2
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_real_agent_graph_checkpoints_principal_and_history_on_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production graph (Principal, messages, tool results) round-trips through the checkpointer."""
    from shopagent.agent.graph import build_agent_graph
    from shopagent.agent.nodes import agent as agent_module
    from shopagent.core.clock import get_clock
    from shopagent.core.principal import Principal
    from shopagent.infra.db.tables import Base
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    class OneShotModel:
        def bind_tools(self, tools):  # type: ignore[no-untyped-def]
            return self

        async def ainvoke(self, messages, **_):  # type: ignore[no-untyped-def]
            return AIMessage(content="Dạ ShopLab xin chào quý khách ạ.")

    monkeypatch.setattr(agent_module, "get_chat_model", lambda role="agent_primary": OneShotModel())

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    handle = await open_postgres_checkpointer(POSTGRES_URL)
    conversation_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": conversation_id}}
    try:
        graph = build_agent_graph(checkpointer=handle.saver)
        async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as session:
            cfg["configurable"]["session"] = session
            for text in ("Xin chào", "Cảm ơn shop"):
                out = await graph.ainvoke(
                    {
                        "conversation_id": conversation_id,
                        "messages": [HumanMessage(content=text)],
                        "principal": Principal.guest(),
                        "clock": get_clock().now(),
                    },
                    cfg,
                )
                assert out["verified_output"]
        snapshot = await graph.aget_state(cfg)
        history = [m.content for m in snapshot.values["messages"]]
        assert history[0] == "Xin chào" and "Cảm ơn shop" in history
        assert len(history) == 4
        assert snapshot.values["principal"].is_guest
    finally:
        await handle.close()
        await engine.dispose()
