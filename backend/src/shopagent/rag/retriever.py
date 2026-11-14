"""Policy retriever in two stages: a candidate source picks the clauses worth a closer look, a reranker orders them.

The first stage is a seam (CandidateSource). By default it is hybrid: BM25 over the normalised query fused by rank
with dense BGE-M3 similarity (HybridCandidates), falling back to BM25 alone when no embedder is configured. While the
corpus is small enough for the reranker to score all of it this stage cannot change the final order; it starts to
matter once the corpus outgrows the reranker's candidate pool. The second stage is the optional cross-encoder.

Ranking choices are justified by evals/retrieval (the independent query set). The index snapshot (parsed chunks)
is cached per process and revalidated with a cheap fingerprint query, so a lookup no longer reloads
and re-tokenises every clause; reranker results are cached per (query, candidates).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.core.clock import get_clock
from shopagent.infra.db.tables import PolicyChunkModel
from shopagent.rag.chunker import build_chunks_from_clauses
from shopagent.rag.diacritics import build_restorer
from shopagent.rag.embeddings import Embedder, get_configured_embedder
from shopagent.rag.indexer import build_corpus
from shopagent.rag.lexical import Bm25Index, normalize_query
from shopagent.rag.reranker import Reranker, RerankSettings, get_configured_reranker

logger = logging.getLogger(__name__)

RRF_K = 60  # reciprocal-rank-fusion constant; 60 is the value from the original paper and is not tuned here

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
        self.matrix_by_ids: dict[tuple[str, ...], Any] = {}
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


class CandidateSource(Protocol):
    """First stage: from the clauses in force, those worth a closer look, best first.

    Returns an empty list when nothing in the corpus relates to the query, which the caller reports as
    "no evidence" rather than presenting a loosely related clause.
    """

    def candidates(self, snapshot: _Snapshot, chunks: list[dict[str, Any]], query: str) -> list[dict[str, Any]]: ...


class Bm25Candidates:
    """Okapi BM25 over accent-stripped tokens; the index per set of clauses in force is cached on the snapshot."""

    def candidates(self, snapshot: _Snapshot, chunks: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        ids = tuple(f"{c['clause_id']}@{c['version']}" for c in chunks)
        index = snapshot.index_by_ids.get(ids)
        if index is None:
            index = snapshot.index_by_ids[ids] = Bm25Index([c["text"] for c in chunks])
        scores = index.scores(query)
        if max(scores) == 0.0:
            return []  # no query term occurs in any clause
        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        return [{**chunks[i], "score": scores[i]} for i in order]


class _Auto:
    """Marker: resolve the embedder from config at call time."""


_AUTO = _Auto()


class HybridCandidates:
    """BM25 and dense similarity, fused by reciprocal rank; the first stage of the default retriever.

    BM25 stays the gatekeeper: when no query term occurs in any clause the answer is "nothing relevant", exactly as
    for BM25 alone, because a dense model always finds a nearest clause even for a question about the weather. The
    reranker's score threshold is what rejects questions that merely resemble the policy.

    Dense search is skipped, with a warning, when the stored vectors come from a different model than the query
    embedder (the index needs `index-policies`); retrieval then continues on BM25 rather than comparing vectors that
    do not belong together.
    """

    def __init__(self, embedder: Embedder | None | _Auto = _AUTO) -> None:
        self._embedder = embedder
        self._lexical = Bm25Candidates()
        self._warned = False

    def _resolve(self) -> Embedder | None:
        return get_configured_embedder() if isinstance(self._embedder, _Auto) else self._embedder

    def candidates(self, snapshot: _Snapshot, chunks: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        lexical = self._lexical.candidates(snapshot, chunks, query)
        embedder = self._resolve()
        if not lexical or embedder is None:
            return lexical
        if any(c.get("embedding_model") != embedder.name or not c.get("embedding") for c in chunks):
            if not self._warned:
                logger.warning("policy chunks were not embedded with %s: run `index-policies`; using BM25 only", embedder.name)
                self._warned = True
            return lexical

        import numpy as np

        ids = tuple(f"{c['clause_id']}@{c['version']}" for c in chunks)
        matrix = snapshot.matrix_by_ids.get(ids)
        if matrix is None:
            raw = np.asarray([c["embedding"] for c in chunks], dtype=np.float32)
            matrix = snapshot.matrix_by_ids[ids] = raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1e-9)
        vector = np.asarray(embedder.embed_query(snapshot.restore_diacritics(query)), dtype=np.float32)
        similarity = matrix @ (vector / max(float(np.linalg.norm(vector)), 1e-9))

        dense_rank = {ids[i]: rank for rank, i in enumerate(np.argsort(-similarity))}
        by_id = {f"{c['clause_id']}@{c['version']}": c for c in chunks}
        fused = []
        for lexical_rank, candidate in enumerate(lexical):
            key = f"{candidate['clause_id']}@{candidate['version']}"
            score = 1.0 / (RRF_K + lexical_rank + 1) + 1.0 / (RRF_K + dense_rank[key] + 1)
            fused.append({**by_id[key], "score": score})
        return sorted(fused, key=lambda c: c["score"], reverse=True)


class PolicyRetriever:
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
        candidates: CandidateSource | None = None,
    ) -> None:
        if session is None and not in_memory:
            raise ValueError("PolicyRetriever needs a database session, or in_memory=True for offline benchmarks")
        self.session = session
        self._candidate_source: CandidateSource = candidates or HybridCandidates()
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
                chunks = [c for c in build_chunks_from_clauses(build_corpus()) if c["status"] == "active"]
                embedder = get_configured_embedder()
                if embedder is not None:
                    for chunk, vector in zip(chunks, embedder.embed_documents([c["text"] for c in chunks]), strict=True):
                        chunk["embedding"], chunk["embedding_model"] = vector, embedder.name
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
                    func.max(PolicyChunkModel.updated_at),
                    func.max(PolicyChunkModel.effective_from),
                    func.max(PolicyChunkModel.effective_to),
                    func.count(PolicyChunkModel.effective_to),
                ).where(PolicyChunkModel.status == "active")
            )
        ).one()
        if count == 0:
            raise PolicyIndexUnavailableError("policy_chunks is empty: run the policy indexer")
        # Adding, rewriting or retiring a clause moves count or updated_at; expiring one moves effective_to.
        fingerprint = (count, *marks)
        if _snapshot is not None and _snapshot.fresh(fingerprint):
            return _snapshot

        rows = (await self.session.execute(select(PolicyChunkModel).where(PolicyChunkModel.status == "active"))).scalars().all()
        chunks = [
            {
                "clause_id": c.clause_id,
                "topic": c.topic,
                "version": c.version,
                "effective_from": c.effective_from,
                "effective_to": c.effective_to,
                "text": c.text,
                "title": c.title,
                "embedding": c.embedding,
                "embedding_model": c.embedding_model,
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

        normalized = normalize_query(query)
        # Embedding the query is CPU work (about 150 ms); keep it off the event loop like the reranker.
        ranked = await asyncio.to_thread(self._candidate_source.candidates, snapshot, chunks, normalized)
        if not ranked:
            return []  # nothing in the corpus relates to the question: nothing to present as evidence

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
