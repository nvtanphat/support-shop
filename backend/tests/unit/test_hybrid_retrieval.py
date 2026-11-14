"""Hybrid candidate stage: BM25 and dense similarity fused by rank, with BM25 as the gatekeeper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from shopagent.infra.db.tables import Base, PolicyChunkModel
from shopagent.rag import indexer as indexer_module
from shopagent.rag.indexer import sync_policies
from shopagent.rag.retriever import (
    Bm25Candidates,
    HybridCandidates,
    PolicyRetriever,
    _Snapshot,
    clear_retrieval_caches,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.tests.fakes import FakeEmbedder


class QueryAxisEmbedder:
    """Maps every query to one fixed direction so a test controls the dense ranking exactly."""

    def __init__(self, name: str = "axis", direction: list[float] | None = None) -> None:
        self.name = name
        self.direction = direction or [1.0, 0.0, 0.0, 0.0]
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self.direction

    def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        raise AssertionError("candidates() never embeds documents; the index holds their vectors")


def chunk(clause_id: str, text: str, vector: list[float], model: str = "axis") -> dict[str, Any]:
    return {"clause_id": clause_id, "version": "v1", "text": text, "topic": "t", "embedding": vector, "embedding_model": model}


# Lexically B is last (no shared word), densely B is first.
CHUNKS = [
    chunk("A", "alpha beta gamma", [0.0, 1.0, 0.0, 0.0]),
    chunk("C", "alpha beta", [0.0, 0.0, 1.0, 0.0]),
    chunk("D", "alpha", [0.0, 0.0, 0.0, 1.0]),
    chunk("B", "delta", [1.0, 0.0, 0.0, 0.0]),
]


def ids(ranked: list[dict[str, Any]]) -> list[str]:
    return [c["clause_id"] for c in ranked]


def test_bm25_alone_puts_the_semantic_match_last() -> None:
    assert ids(Bm25Candidates().candidates(_Snapshot("s", CHUNKS), CHUNKS, "alpha beta gamma"))[-1] == "B"


def test_dense_similarity_lifts_a_clause_bm25_ranks_last() -> None:
    ranked = HybridCandidates(QueryAxisEmbedder()).candidates(_Snapshot("s", CHUNKS), CHUNKS, "alpha beta gamma")
    assert ids(ranked)[:2] == ["A", "B"] and ids(ranked)[-1] == "D"
    assert ranked[0]["score"] > ranked[-1]["score"] > 0


def test_a_query_sharing_no_term_with_any_clause_is_still_nothing() -> None:
    embedder = QueryAxisEmbedder()
    assert HybridCandidates(embedder).candidates(_Snapshot("s", CHUNKS), CHUNKS, "zzz qqq") == []
    assert embedder.queries == []  # the gate runs first; no point embedding a question nothing relates to


def test_without_an_embedder_it_is_exactly_bm25() -> None:
    snap = _Snapshot("s", CHUNKS)
    assert HybridCandidates(None).candidates(snap, CHUNKS, "alpha beta") == Bm25Candidates().candidates(snap, CHUNKS, "alpha beta")


@pytest.mark.parametrize("stale", ["other-model", ""])
def test_vectors_from_another_model_are_never_compared(stale: str) -> None:
    chunks = [{**c, "embedding_model": stale} for c in CHUNKS]
    embedder = QueryAxisEmbedder()
    snap = _Snapshot("s", chunks)
    assert HybridCandidates(embedder).candidates(snap, chunks, "alpha beta") == Bm25Candidates().candidates(snap, chunks, "alpha beta")
    assert embedder.queries == []


def test_a_chunk_without_a_vector_falls_back_to_bm25() -> None:
    chunks = [{**CHUNKS[0], "embedding": []}, *CHUNKS[1:]]
    assert ids(HybridCandidates(QueryAxisEmbedder()).candidates(_Snapshot("s", chunks), chunks, "alpha beta gamma")) == ids(
        Bm25Candidates().candidates(_Snapshot("s", chunks), chunks, "alpha beta gamma")
    )


def test_the_dense_query_is_embedded_with_diacritics_restored() -> None:
    embedder = QueryAxisEmbedder()
    snap = _Snapshot("s", CHUNKS)
    snap._restorer = lambda q: q.upper()  # type: ignore[assignment]
    HybridCandidates(embedder).candidates(snap, CHUNKS, "alpha beta")
    assert embedder.queries == ["ALPHA BETA"]


# --- through the database ---------------------------------------------------------------------------
@pytest.fixture
async def session():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    clear_retrieval_caches()
    async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as s:
        yield s
    clear_retrieval_caches()
    await engine.dispose()


async def rows(session: AsyncSession) -> list[PolicyChunkModel]:
    return list((await session.execute(select(PolicyChunkModel))).scalars().all())


async def test_indexing_stores_each_vector_with_the_model_that_made_it(session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder("bge-test")
    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: fake)
    await sync_policies(session, docs_dir=tmp_path)
    stored = await rows(session)
    assert len(stored) == 10 and all(r.embedding_model == "bge-test" and len(r.embedding) == 8 for r in stored)


async def test_changing_the_embedding_model_reembeds_everything_once(session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = FakeEmbedder("model-a")
    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: first)
    await sync_policies(session, docs_dir=tmp_path)

    second = FakeEmbedder("model-b")
    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: second)
    report = await sync_policies(session, docs_dir=tmp_path)
    assert len(report.updated) == 10 and len(second.documents) == 10
    assert {r.embedding_model for r in await rows(session)} == {"model-b"}

    again = await sync_policies(session, docs_dir=tmp_path)
    assert not again.updated and len(second.documents) == 10  # nothing more to embed


async def test_with_the_embedder_off_new_chunks_have_no_vector_and_old_ones_are_kept(session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder("model-a")
    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: fake)
    await sync_policies(session, docs_dir=tmp_path)

    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: None)
    (tmp_path / "w.md").write_text("---\nclause_id: POL-WARRANTY-01\ntopic: warranty\n---\nBảo hành mười hai tháng.\n", encoding="utf-8")
    report = await sync_policies(session, docs_dir=tmp_path)
    assert report.added == ["POL-WARRANTY-01@2026-11-01"] and not report.updated
    by_clause = {r.clause_id: r for r in await rows(session)}
    assert by_clause["POL-WARRANTY-01"].embedding == [] and by_clause["POL-WARRANTY-01"].embedding_model == ""
    assert by_clause["POL-RETURN-01"].embedding_model == "model-a" and len(by_clause["POL-RETURN-01"].embedding) == 8


async def test_the_retriever_uses_the_stored_vectors(session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder("bge-test")
    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: fake)
    await sync_policies(session, docs_dir=tmp_path)
    fake.queries.clear()
    results = await PolicyRetriever(session=session, candidates=HybridCandidates(fake)).retrieve("mình muốn trả hàng đổi ý", top_k=3)
    assert results and len(fake.queries) == 1 and fake.documents  # the query was embedded; documents came from the table
