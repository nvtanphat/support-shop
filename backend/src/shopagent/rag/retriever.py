"""Hybrid policy retriever combining lexical unaccented search and semantic embeddings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.infra.db.tables import PolicyChunkModel
from shopagent.rag.chunker import (
    build_chunks_from_clauses,
    remove_vietnamese_accents,
    tokenize_unaccent,
)
from shopagent.rag.embeddings import get_embedding_provider
from shopagent.rag.generator import generate_policy_clauses


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    return max(0.0, dot)


class HybridRetriever:
    """Retrieves top-k relevant policy clauses using BM25 lexical + Cosine semantic RRF."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.embedder = get_embedding_provider()
        self._in_memory_cache: list[dict[str, Any]] | None = None

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
        """Fetch policy chunks from DB, or fallback to in-memory generated clauses."""
        if self.session is not None:
            try:
                stmt = select(PolicyChunkModel)
                if as_of:
                    stmt = stmt.where(
                        PolicyChunkModel.effective_from <= as_of,
                        (PolicyChunkModel.effective_to.is_(None) | (PolicyChunkModel.effective_to > as_of)),
                    )
                res = await self.session.execute(stmt)
                db_chunks = res.scalars().all()
                if db_chunks:
                    return [
                        {
                            "clause_id": c.clause_id,
                            "topic": c.topic,
                            "text": c.text,
                            "text_unaccent": c.text_unaccent,
                            "tokens": tokenize_unaccent(c.text_unaccent),
                            "embedding": c.embedding,
                        }
                        for c in db_chunks
                    ]
            except Exception:
                pass

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
        for idx, c in enumerate(chunks):
            c_tokens = set(c["tokens"])
            overlap = len(query_tokens.intersection(c_tokens))
            bonus = 0.0
            # Phrase / exact substring match boost
            if query_unaccent in c["text_unaccent"]:
                bonus += 5.0
            score = overlap + bonus
            lexical_scores.append((idx, score))

        # Sort lexical descending
        lexical_scores.sort(key=lambda x: x[1], reverse=True)
        lexical_ranks = {item[0]: rank for rank, item in enumerate(lexical_scores)}

        # 2. Semantic Scoring (Cosine similarity)
        semantic_scores = []
        for idx, c in enumerate(chunks):
            sim = _cosine_similarity(query_emb, c["embedding"])
            semantic_scores.append((idx, sim))

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

        results = []
        for idx, score in rrf_list[:top_k]:
            c = chunks[idx]
            results.append({
                "clause_id": c["clause_id"],
                "topic": c["topic"],
                "text": c["text"],
                "score": round(score, 4),
            })

        return results
