"""Hybrid policy retriever combining lexical unaccented search and semantic embeddings."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.infra.db.tables import PolicyChunkModel
from shopagent.rag.chunker import (
    build_chunks_from_clauses,
    remove_vietnamese_accents,
    tokenize_unaccent,
)
from shopagent.rag.embeddings import get_embedding_provider
from shopagent.rag.generator import generate_policy_clauses
from shopagent.rag.reranker import Reranker, get_configured_reranker


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    return max(0.0, dot)


def _format_datetime(dt: Any) -> str | None:
    """Safely format an optional datetime or string into ISO string."""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return str(dt.isoformat())
    return str(dt)


class PolicyIndexUnavailableError(RuntimeError):
    """The policy index holds no clauses at all: retrieval cannot say anything about policy.

    This is different from "no relevant evidence", which means the index works but nothing
    in it answers the question.
    """


class HybridRetriever:
    """Retrieves top-k relevant policy clauses using BM25 lexical + Cosine semantic RRF.

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
    ) -> None:
        if session is None and not in_memory:
            raise ValueError("HybridRetriever needs a database session, or in_memory=True for offline benchmarks")
        self.session = session
        self._explicit_reranker = reranker
        self._explicit_candidates = rerank_candidates
        self.embedder = get_embedding_provider()
        self._in_memory_cache: list[dict[str, Any]] | None = None

    def _resolve_reranker(self) -> tuple[Reranker | None, int]:
        """An explicitly injected reranker, else the configured one; failure to load raises."""
        if self._explicit_reranker is not None:
            return self._explicit_reranker, self._explicit_candidates
        configured = get_configured_reranker()
        return configured if configured is not None else (None, self._explicit_candidates)

    def _get_in_memory_chunks(self, as_of: datetime | None = None) -> list[dict[str, Any]]:
        if self._in_memory_cache is None:
            clauses = generate_policy_clauses()
            chunks = build_chunks_from_clauses(clauses)
            texts = [c["text"] for c in chunks]
            embeddings = self.embedder.embed_documents(texts)
            for c, emb in zip(chunks, embeddings, strict=False):
                c["embedding"] = emb
            self._in_memory_cache = chunks

        if as_of is not None:
            filtered = []
            for c in self._in_memory_cache:
                eff_from = c.get("effective_from")
                eff_to = c.get("effective_to")
                if isinstance(eff_from, str):
                    try:
                        eff_from = datetime.fromisoformat(eff_from.replace("Z", "+00:00"))
                    except Exception:
                        eff_from = None
                if isinstance(eff_to, str):
                    try:
                        eff_to = datetime.fromisoformat(eff_to.replace("Z", "+00:00"))
                    except Exception:
                        eff_to = None

                # Normalize timezone if needed
                as_of_cmp = as_of
                if eff_from and eff_from.tzinfo is not None and as_of_cmp.tzinfo is None:
                    as_of_cmp = as_of_cmp.replace(tzinfo=eff_from.tzinfo)
                elif eff_from and eff_from.tzinfo is None and as_of_cmp.tzinfo is not None:
                    as_of_cmp = as_of_cmp.replace(tzinfo=None)

                if eff_from and as_of_cmp < eff_from:
                    continue
                if eff_to and as_of_cmp >= eff_to:
                    continue
                filtered.append(c)
            return filtered

        return self._in_memory_cache

    async def _fetch_chunks(self, as_of: datetime | None = None) -> list[dict[str, Any]]:
        """Fetch policy chunks from the database, or from the generated clauses in offline mode."""
        if self.session is not None:
            total = (await self.session.execute(select(func.count()).select_from(PolicyChunkModel))).scalar_one()
            if total == 0:
                raise PolicyIndexUnavailableError("policy_chunks is empty: run the policy indexer")
            stmt = select(PolicyChunkModel)
            if as_of:
                stmt = stmt.where(
                    PolicyChunkModel.effective_from <= as_of,
                    (PolicyChunkModel.effective_to.is_(None) | (PolicyChunkModel.effective_to > as_of)),
                )
            res = await self.session.execute(stmt)
            db_chunks = res.scalars().all()
            return [
                {
                    "clause_id": c.clause_id,
                    "topic": c.topic,
                    "version": c.version,
                    "effective_from": _format_datetime(c.effective_from),
                    "effective_to": _format_datetime(c.effective_to),
                    "text": c.text,
                    "text_unaccent": c.text_unaccent,
                    "tokens": tokenize_unaccent(c.text_unaccent),
                    "embedding": c.embedding,
                }
                for c in db_chunks
            ]

        return self._get_in_memory_chunks(as_of=as_of)

    async def retrieve(
        self,
        query: str,
        top_k: int = 4,
        topic: str | None = None,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top_k matching clauses using Reciprocal Rank Fusion."""
        chunks = await self._fetch_chunks(as_of=as_of)
        if not chunks:
            return []

        # Filter by topic if specified
        if topic:
            filtered = [c for c in chunks if c.get("topic") == topic]
            if filtered:
                chunks = filtered

        query_unaccent = remove_vietnamese_accents(query)
        query_tokens = set(tokenize_unaccent(query))
        query_emb = self.embedder.embed_query(query)

        # 1. Lexical Scoring (BM25 token overlap + exact match boost)
        lexical_scores = []
        max_overlap = 0
        for idx, c in enumerate(chunks):
            c_tokens = set(c["tokens"])
            overlap = len(query_tokens.intersection(c_tokens))
            if overlap > max_overlap:
                max_overlap = overlap
            bonus = 0.0
            # Phrase / exact substring match boost
            if query_unaccent in c["text_unaccent"]:
                bonus += 5.0
            score = overlap + bonus
            lexical_scores.append((idx, score))

        # 2. Semantic Scoring (Cosine similarity)
        semantic_scores = []
        max_sim = 0.0
        for idx, c in enumerate(chunks):
            sim = _cosine_similarity(query_emb, c["embedding"])
            if sim > max_sim:
                max_sim = sim
            semantic_scores.append((idx, sim))

        # If zero token overlap and no phrase match, treat as no relevant evidence
        if max_overlap == 0:
            return []

        # Sort lexical descending
        lexical_scores.sort(key=lambda x: x[1], reverse=True)
        lexical_ranks = {item[0]: rank for rank, item in enumerate(lexical_scores)}

        # Sort semantic descending
        semantic_scores.sort(key=lambda x: x[1], reverse=True)
        semantic_ranks = {item[0]: rank for rank, item in enumerate(semantic_scores)}

        # 3. Reciprocal Rank Fusion (RRF)
        k_const = 60
        rrf_list = []
        for idx in range(len(chunks)):
            r_lex = lexical_ranks[idx]
            r_sem = semantic_ranks[idx]
            rrf_score = (1.0 / (k_const + r_lex)) + (1.0 / (k_const + r_sem))
            rrf_list.append((idx, rrf_score))

        rrf_list.sort(key=lambda x: x[1], reverse=True)

        reranker, candidates = self._resolve_reranker()
        if reranker is not None:
            pool = rrf_list[: max(top_k, candidates)]
            rerank_scores = await asyncio.to_thread(
                reranker.scores, query, [chunks[idx]["text"] for idx, _ in pool]
            )
            rrf_list = [
                (idx, score)
                for (idx, _), score in sorted(zip(pool, rerank_scores, strict=True), key=lambda p: p[1], reverse=True)
            ]

        results = []
        for idx, score in rrf_list[:top_k]:
            c = chunks[idx]
            results.append({
                "clause_id": c["clause_id"],
                "topic": c["topic"],
                "version": c["version"],
                "effective_from": _format_datetime(c.get("effective_from")),
                "effective_to": _format_datetime(c.get("effective_to")),
                "text": c["text"],
                "score": round(score, 4),
            })

        return results
