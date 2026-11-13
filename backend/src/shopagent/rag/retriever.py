"""Policy retriever: BM25 over normalised queries, optional cross-encoder reranking, cached index.

Ranking choices are justified by evals/retrieval (the independent query set). The index snapshot (parsed chunks)
is cached per process and revalidated with a cheap fingerprint query, so a lookup no longer reloads
and re-tokenises every clause; reranker results are cached per (query, candidates).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.infra.db.tables import PolicyChunkModel
from shopagent.rag.chunker import build_chunks_from_clauses
from shopagent.rag.diacritics import build_restorer
from shopagent.rag.generator import generate_policy_clauses
from shopagent.rag.lexical import Bm25Index, normalize_query
from shopagent.rag.reranker import Reranker, RerankSettings, get_configured_reranker

# The snapshot is also revalidated by fingerprint on every call; the TTL bounds staleness if the
# fingerprint query ever misses a change.
SNAPSHOT_TTL_SECONDS = 300.0
RERANK_CACHE_SIZE = 256


def _format_datetime(dt: Any) -> str | None:
    if dt is None:
        return None
    return str(dt.isoformat()) if hasattr(dt, "isoformat") else str(dt)


def _as_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value  # type: ignore[no-any-return]
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _aware(dt: datetime, reference: datetime) -> datetime:
    """Compare naive database timestamps (SQLite) with aware ones without guessing a zone."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    if dt.tzinfo is not None and reference.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


class PolicyIndexUnavailableError(RuntimeError):
    """The policy index holds no clauses at all: retrieval cannot say anything about policy.

    This is different from "no relevant evidence", which means the index works but nothing
    in it answers the question.
    """


class _Snapshot:
    def __init__(self, fingerprint: object, chunks: list[dict[str, Any]]) -> None:
        self.fingerprint = fingerprint
        self.chunks = chunks
        self.loaded_at = time.monotonic()
        self.index_by_ids: dict[tuple[str, ...], Bm25Index] = {}
        self._restorer: Callable[[str], str] | None = None

    def restore_diacritics(self, query: str) -> str:
        if self._restorer is None:
            self._restorer = build_restorer(c["text"] for c in self.chunks)
        return self._restorer(query)

    def fresh(self, fingerprint: object) -> bool:
        return fingerprint == self.fingerprint and time.monotonic() - self.loaded_at < SNAPSHOT_TTL_SECONDS


_snapshot: _Snapshot | None = None
_rerank_cache: OrderedDict[tuple[int, str, tuple[str, ...]], list[float]] = OrderedDict()


def clear_retrieval_caches() -> None:
    """Drop cached index snapshots and rerank results (used after re-indexing and in tests)."""
    global _snapshot
    _snapshot = None
    _rerank_cache.clear()


class HybridRetriever:
    """Retrieves the top-k policy clauses that were in force at `as_of`.

    Production code passes a database session. `in_memory=True` is an explicit offline mode for
    benchmarks; it is never selected implicitly when a database call fails.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        in_memory: bool = False,
        reranker: Reranker | None = None,
        rerank_candidates: int = 10,
        min_rerank_score: float | None = None,
    ) -> None:
        if session is None and not in_memory:
            raise ValueError("HybridRetriever needs a database session, or in_memory=True for offline benchmarks")
        self.session = session
        self._explicit_reranker = reranker
        self._explicit_candidates = rerank_candidates
        self._explicit_min_score = min_rerank_score
        self._in_memory_snapshot: _Snapshot | None = None

    def _resolve_reranker(self) -> RerankSettings | None:
        """An explicitly injected reranker, else the configured one; failure to load raises."""
        if self._explicit_reranker is not None:
            return RerankSettings(self._explicit_reranker, self._explicit_candidates, self._explicit_min_score)
        return get_configured_reranker()

    async def _load_snapshot(self) -> _Snapshot:
        global _snapshot
        if self.session is None:
            if self._in_memory_snapshot is None:
                chunks = build_chunks_from_clauses(generate_policy_clauses())
                for chunk in chunks:
                    chunk["effective_from"] = _as_datetime(chunk.get("effective_from"))
                    chunk["effective_to"] = _as_datetime(chunk.get("effective_to"))
                self._in_memory_snapshot = _Snapshot("in-memory", chunks)
            return self._in_memory_snapshot

        count, *marks = (
            await self.session.execute(
                select(
                    func.count(PolicyChunkModel.id),
                    func.max(PolicyChunkModel.created_at),
                    func.max(PolicyChunkModel.effective_from),
                    func.max(PolicyChunkModel.effective_to),
                    func.count(PolicyChunkModel.effective_to),
                )
            )
        ).one()
        if count == 0:
            raise PolicyIndexUnavailableError("policy_chunks is empty: run the policy indexer")
        # Re-indexing adds rows and expiring a clause moves effective_to; both change the fingerprint.
        fingerprint = (count, *marks)
        if _snapshot is not None and _snapshot.fresh(fingerprint):
            return _snapshot

        rows = (await self.session.execute(select(PolicyChunkModel))).scalars().all()
        chunks = [
            {
                "clause_id": c.clause_id,
                "topic": c.topic,
                "version": c.version,
                "effective_from": c.effective_from,
                "effective_to": c.effective_to,
                "text": c.text,
            }
            for c in rows
        ]
        _snapshot = _Snapshot(fingerprint, chunks)
        return _snapshot

    @staticmethod
    def _in_force(chunks: list[dict[str, Any]], as_of: datetime) -> list[dict[str, Any]]:
        visible = []
        for c in chunks:
            start, end = c.get("effective_from"), c.get("effective_to")
            if start is not None and _aware(as_of, start) < start:
                continue
            if end is not None and _aware(as_of, end) >= end:
                continue
            visible.append(c)
        return visible

    async def _rerank(self, reranker: Reranker, query: str, pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        key = (id(reranker), query, tuple(f"{c['clause_id']}@{c['version']}" for c in pool))
        scores = _rerank_cache.get(key)
        if scores is None:
            scores = await asyncio.to_thread(reranker.scores, query, [c["text"] for c in pool])
            _rerank_cache[key] = scores
            while len(_rerank_cache) > RERANK_CACHE_SIZE:
                _rerank_cache.popitem(last=False)
        else:
            _rerank_cache.move_to_end(key)
        ranked = sorted(zip(pool, scores, strict=True), key=lambda pair: pair[1], reverse=True)
        return [{**chunk, "score": score} for chunk, score in ranked]

    async def retrieve(
        self,
        query: str,
        top_k: int = 4,
        topic: str | None = None,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to top_k clauses in force at `as_of` (default: now), best first."""
        snapshot = await self._load_snapshot()
        chunks = self._in_force(snapshot.chunks, as_of or get_clock().now())
        if topic:
            chunks = [c for c in chunks if c.get("topic") == topic] or chunks
        if not chunks:
            return []

        ids = tuple(f"{c['clause_id']}@{c['version']}" for c in chunks)
        index = snapshot.index_by_ids.get(ids)
        if index is None:
            index = snapshot.index_by_ids[ids] = Bm25Index([c["text"] for c in chunks])
        normalized = normalize_query(query)
        scores = index.scores(normalized)
        if max(scores) == 0.0:
            return []  # no query term occurs in any clause: nothing to present as evidence

        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        ranked = [{**chunks[i], "score": scores[i]} for i in order]
        settings = self._resolve_reranker()
        if settings is not None:
            pool = ranked[: max(top_k, settings.candidates)]
            # The cross-encoder reads natural text: restore diacritics a customer left out.
            ranked = await self._rerank(settings.reranker, snapshot.restore_diacritics(normalized), pool)
            if settings.min_score is not None and ranked[0]["score"] < settings.min_score:
                return []  # the best clause is still too weak to present as evidence

        return [
            {
                "clause_id": c["clause_id"],
                "topic": c["topic"],
                "version": c["version"],
                "effective_from": _format_datetime(c.get("effective_from")),
                "effective_to": _format_datetime(c.get("effective_to")),
                "text": c["text"],
                "score": round(float(c["score"]), 4),
            }
            for c in ranked[:top_k]
        ]
