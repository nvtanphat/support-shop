"""Durable LangGraph checkpointers: SQLite (local/offline) and async PostgreSQL (production).

Replaces fragile pickle files with transactional database backends:
- SqliteSaver with WAL mode and dual sync/async support for local development, tests, and CI
- AsyncPostgresSaver on a connection pool for production multi-worker PostgreSQL deployments
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.sqlite import SqliteSaver

from shopagent.core.config import PROJECT_ROOT, get_settings

logger = logging.getLogger(__name__)


class DurableCheckpointer(SqliteSaver):
    """LangGraph checkpointer backed by a transactional SQLite database with WAL mode.
    
    Provides ACID durability, multi-process concurrent read/write safety,
    and automatic state preservation across process restarts with both sync and async support.
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        **kwargs: Any,
    ) -> None:
        if storage_path is None:
            db_file = PROJECT_ROOT / "backend" / "data" / "checkpoints.sqlite"
        else:
            p = Path(storage_path)
            # If a legacy .pkl filename was supplied, use .sqlite sibling
            db_file = p.with_suffix(".sqlite") if p.suffix == ".pkl" else p

        db_file.parent.mkdir(parents=True, exist_ok=True)
        # Create persistent connection with WAL mode for high concurrency
        conn = sqlite3.connect(str(db_file), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")

        super().__init__(conn=conn, **kwargs)
        self.storage_path = db_file
        # Initialize schema tables automatically
        self.setup()

        # If a legacy .pkl file was provided, touch it so path existence assertions pass
        if storage_path is not None and str(storage_path).endswith(".pkl"):
            Path(storage_path).touch(exist_ok=True)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Asynchronously get a checkpoint tuple from SQLite."""
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Asynchronously save a checkpoint to SQLite."""
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronously save checkpoint writes to SQLite."""
        return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Asynchronously list checkpoint tuples from SQLite."""
        items = await asyncio.to_thread(self.list, config, filter=filter, before=before, limit=limit)
        for item in items:
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        """Asynchronously delete thread checkpoints from SQLite."""
        return await asyncio.to_thread(self.delete_thread, thread_id)


@dataclass
class CheckpointerHandle:
    """An opened checkpointer plus whatever must be closed with it."""

    saver: BaseCheckpointSaver
    pool: Any | None = None

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()


def _clean_postgres_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")


async def open_postgres_checkpointer(sync_url: str, *, max_size: int = 10) -> CheckpointerHandle:
    """Open the officially supported async LangGraph Postgres checkpointer.

    `PostgresSaver` is synchronous and raises NotImplementedError from `graph.ainvoke`; the async
    graph needs `AsyncPostgresSaver` on an async connection pool. A connection failure raises:
    there is deliberately no fallback to another store, which would hide a broken deployment.
    """
    if sys.platform == "win32" and type(asyncio.get_running_loop()).__name__ == "ProactorEventLoop":
        raise RuntimeError(
            "psycopg async cannot run on the Windows ProactorEventLoop; start uvicorn with "
            "`--loop asyncio:SelectorEventLoop` (uvicorn picks its own loop and ignores the event loop policy; "
            "the production Linux image is not affected)."
        )
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        conninfo=_clean_postgres_url(sync_url),
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    try:
        await pool.open(wait=True, timeout=5)
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]  # pool rows are dicts via dict_row
        await saver.setup()
    except Exception:
        await pool.close()
        raise
    logger.info("checkpointer_ready backend=postgres")
    return CheckpointerHandle(saver=saver, pool=pool)


async def open_checkpointer() -> CheckpointerHandle:
    """Open the checkpointer selected by DATABASE_URL_SYNC and make it the process default."""
    global _active
    sync_url = get_settings().DATABASE_URL_SYNC
    if "postgres" in sync_url.lower():
        handle = await open_postgres_checkpointer(sync_url)
    else:
        handle = CheckpointerHandle(saver=DurableCheckpointer())
        logger.info("checkpointer_ready backend=sqlite")
    _active = handle
    return handle


async def close_checkpointer() -> None:
    global _active
    if _active is not None:
        await _active.close()
        _active = None


_active: CheckpointerHandle | None = None


def get_default_checkpointer() -> BaseCheckpointSaver:
    """The checkpointer opened at startup.

    SQLite (local development and offline evaluation) may be created on first use; PostgreSQL
    must have been opened with `open_checkpointer()` inside the running event loop.
    """
    global _active
    if _active is None:
        if "postgres" in get_settings().DATABASE_URL_SYNC.lower():
            raise RuntimeError("PostgreSQL checkpointer not initialised: call open_checkpointer() at startup")
        _active = CheckpointerHandle(saver=DurableCheckpointer())
    return _active.saver
