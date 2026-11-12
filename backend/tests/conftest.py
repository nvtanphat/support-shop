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
