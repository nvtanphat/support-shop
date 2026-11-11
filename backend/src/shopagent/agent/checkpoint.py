"""Durable Checkpointer for LangGraph with disk persistence across process restarts."""

from __future__ import annotations

import os
from pathlib import Path
import pickle
import tempfile
from typing import Any
from collections import defaultdict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
)
from langgraph.checkpoint.memory import InMemorySaver


class DurableCheckpointer(InMemorySaver):
    """LangGraph checkpointer with automatic atomic snapshot persistence on disk.
    
    Preserves checkpoints, multi-turn states, and pending writes across server restarts.
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if storage_path is None:
            from shopagent.core.config import PROJECT_ROOT
            self.storage_path = PROJECT_ROOT / "backend" / "data" / "checkpoints.pkl"
        else:
            self.storage_path = Path(storage_path)

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load persisted state if file exists."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "rb") as f:
                data = pickle.load(f)
                if isinstance(data, dict):
                    storage_raw = data.get("storage", {})
                    writes_raw = data.get("writes", {})
                    blobs_raw = data.get("blobs", {})

                    # Reconstruct defaultdict structures with proper inner factories
                    self.storage = defaultdict(lambda: defaultdict(dict))
                    for thread_id, ns_dict in storage_raw.items():
                        self.storage[thread_id] = defaultdict(dict, ns_dict)
                    self.writes = defaultdict(dict, writes_raw)
                    self.blobs = defaultdict(None, blobs_raw)
        except Exception:
            # If corrupted or version mismatch, start clean and overwrite on next write
            pass

    def _save_to_disk(self) -> None:
        """Atomic snapshot write to disk."""
        try:
            dump_data = {
                "storage": dict(self.storage),
                "writes": dict(self.writes),
                "blobs": dict(self.blobs),
            }
            dir_name = self.storage_path.parent
            dir_name.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("wb", dir=dir_name, delete=False) as tmp:
                pickle.dump(dump_data, tmp, protocol=pickle.HIGHEST_PROTOCOL)
                tmp_name = tmp.name
            os.replace(tmp_name, self.storage_path)
        except Exception:
            pass

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        res = super().put(config, checkpoint, metadata, new_versions)
        self._save_to_disk()
        return res

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        res = await super().aput(config, checkpoint, metadata, new_versions)
        self._save_to_disk()
        return res

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path)
        self._save_to_disk()

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        await super().aput_writes(config, writes, task_id, task_path)
        self._save_to_disk()

    def delete_thread(self, thread_id: str) -> None:
        super().delete_thread(thread_id)
        self._save_to_disk()

    async def adelete_thread(self, thread_id: str) -> None:
        await super().adelete_thread(thread_id)
        self._save_to_disk()


_durable_checkpointer: DurableCheckpointer | None = None


def get_default_checkpointer() -> DurableCheckpointer:
    """Singleton getter for durable persistent checkpointer."""
    global _durable_checkpointer
    if _durable_checkpointer is None:
        _durable_checkpointer = DurableCheckpointer()
    return _durable_checkpointer
