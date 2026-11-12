"""Pytest configuration for backend test suite."""

from __future__ import annotations

import asyncio
import os
import sys

# Set default test environment variables before any test runs
os.environ.setdefault("LLM_PRIMARY_PROVIDER", "fake")
os.environ.setdefault("LLM_FALLBACK_PROVIDER", "fake")
os.environ.setdefault("INTEGRATION_MODE", "simulated")
# Unit and integration tests never download or run the cross-encoder model.
os.environ.setdefault("RETRIEVAL_RERANKER_ENABLED", "false")

# psycopg's async driver (LangGraph AsyncPostgresSaver) cannot run on the Windows ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def in_memory_checkpointer(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Give each test its own checkpointer, whatever DATABASE_URL_SYNC points at (CI uses PostgreSQL).

    Production opens the async PostgreSQL checkpointer in the app lifespan; tests that exercise that
    path pass a real saver explicitly (see integration/test_checkpoint_postgres.py).
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from shopagent.agent import checkpoint, graph

    monkeypatch.setattr(checkpoint, "_active", checkpoint.CheckpointerHandle(saver=InMemorySaver()))
    monkeypatch.setattr(graph, "_compiled_graph", None)
    yield
