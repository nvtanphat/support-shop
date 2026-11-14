"""The policy corpus can grow: documents load, bad data is refused, indexing rewrites only what changed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from shopagent.agent.tools.definitions import _within_budget
from shopagent.infra.db.tables import Base, PolicyChunkModel
from shopagent.rag import indexer as indexer_module
from shopagent.rag.documents import (
    MAX_CLAUSE_CHARS,
    PolicyDocumentError,
    load_documents,
    validate_clauses,
)
from shopagent.rag.indexer import sync_policies
from shopagent.rag.retriever import PolicyRetriever, clear_retrieval_caches
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.tests.fakes import FakeEmbedder  # noqa: E402

RULES = {"version": "2026-11-01", "effective_from": "2026-11-01T00:00:00+07:00"}


def write_doc(directory: Path, name: str, clause_id: str, body: str, **header: Any) -> None:
    meta = {"clause_id": clause_id, "topic": "warranty", **header}
    lines = "\n".join(f"{k}: {v}" for k, v in meta.items())
    (directory / name).write_text(f"---\n{lines}\n---\n{body}\n", encoding="utf-8")


def clause(cid: str = "POL-TEST-01", **over: Any) -> dict[str, Any]:
    return {"clause_id": cid, "topic": "test", "version": "v1", "effective_from": "2026-11-01T00:00:00", "effective_to": None,
            "text": "Nội dung hợp lệ.", "status": "active", "source": "x.md", **over}


# --- documents ----------------------------------------------------------------------------------------
def test_a_document_loads_with_defaults_from_the_rules(tmp_path: Path) -> None:
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Bảo hành tai nghe 12 tháng.", title="Bảo hành")
    [c] = load_documents(RULES, tmp_path)
    assert c["clause_id"] == "POL-WARRANTY-01" and c["version"] == "2026-11-01" and c["status"] == "active"
    assert c["category_scope"] == ["all"] and c["source"] == "policy/docs/w.md" and c["title"] == "Bảo hành"


def test_a_document_without_a_header_is_refused(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text("Không có phần đầu.", encoding="utf-8")
    with pytest.raises(PolicyDocumentError, match="missing the '---' YAML header"):
        load_documents(RULES, tmp_path)


def test_a_missing_documents_directory_means_no_documents(tmp_path: Path) -> None:
    assert load_documents(RULES, tmp_path / "nope") == []


@pytest.mark.parametrize(
    ("clauses", "problem"),
    [
        ([clause("TOPIC-1")], "clause_id must look like"),
        ([clause(text="   ")], "text is empty"),
        ([clause(text="x" * (MAX_CLAUSE_CHARS + 1))], "the limit is"),
        ([clause(), clause()], "defined more than once"),
        ([clause(text="Xem POL-NOPE-09.")], "which does not exist"),
        ([clause(parent_id="POL-NOPE-09")], "parent_id POL-NOPE-09 does not exist"),
        ([clause(parent_id="POL-TEST-01")], "points to itself"),
        ([clause(effective_to="2026-10-01T00:00:00")], "effective_to is not after"),
        ([clause(status="draft")], "status must be one of"),
        ([clause(version="v1"), clause(version="v2", effective_from="2026-12-01T00:00:00")], "in force at the same time"),
    ],
)
def test_inconsistent_clauses_are_refused(clauses: list[dict[str, Any]], problem: str) -> None:
    with pytest.raises(PolicyDocumentError, match=problem):
        validate_clauses(clauses)


def test_consecutive_versions_that_do_not_overlap_are_accepted() -> None:
    validate_clauses([
        clause(version="v1", effective_to="2026-12-01T00:00:00"),
        clause(version="v2", effective_from="2026-12-01T00:00:00"),
    ])


def test_every_problem_is_listed_not_just_the_first() -> None:
    with pytest.raises(PolicyDocumentError) as exc:
        validate_clauses([clause("BAD"), clause(text="")])
    assert len(exc.value.problems) >= 2


# --- incremental indexing -----------------------------------------------------------------------------
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


@pytest.fixture
def embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    """The embedder the indexer uses, so 'only changed chunks are embedded' is observable."""
    fake = FakeEmbedder()
    monkeypatch.setattr(indexer_module, "get_configured_embedder", lambda: fake)
    return fake


async def test_a_second_index_run_changes_nothing_and_embeds_nothing(session: AsyncSession, embedder: FakeEmbedder, tmp_path: Path) -> None:
    first = await sync_policies(session, docs_dir=tmp_path)
    assert len(first.added) == 10 and not first.unchanged
    embedder.documents.clear()
    second = await sync_policies(session, docs_dir=tmp_path)
    assert not second.added and not second.updated and len(second.unchanged) == 10
    assert embedder.documents == []


async def test_adding_a_document_adds_only_that_clause(session: AsyncSession, embedder: FakeEmbedder, tmp_path: Path) -> None:
    await sync_policies(session, docs_dir=tmp_path)
    embedder.documents.clear()
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Tai nghe được bảo hành mười hai tháng kể từ ngày mua.")
    report = await sync_policies(session, docs_dir=tmp_path)
    assert report.added == ["POL-WARRANTY-01@2026-11-01"] and len(report.unchanged) == 10 and not report.updated
    assert len(embedder.documents) == 1
    assert len(report.active) == 11


async def test_editing_a_document_rewrites_and_reembeds_only_that_clause(session: AsyncSession, embedder: FakeEmbedder, tmp_path: Path) -> None:
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Bảo hành mười hai tháng.")
    await sync_policies(session, docs_dir=tmp_path)
    embedder.documents.clear()
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Bảo hành hai mươi bốn tháng.")
    report = await sync_policies(session, docs_dir=tmp_path)
    assert report.updated == ["POL-WARRANTY-01@2026-11-01"] and not report.added and len(embedder.documents) == 1
    row = (await session.execute(select(PolicyChunkModel).where(PolicyChunkModel.clause_id == "POL-WARRANTY-01"))).scalar_one()
    assert "hai mươi bốn" in row.text and row.source == "policy/docs/w.md"


async def test_a_removed_document_is_retired_not_deleted(session: AsyncSession, tmp_path: Path) -> None:
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Bảo hành mười hai tháng.")
    await sync_policies(session, docs_dir=tmp_path)
    (tmp_path / "w.md").unlink()
    report = await sync_policies(session, docs_dir=tmp_path)
    assert report.retired == ["POL-WARRANTY-01@2026-11-01"]
    row = (await session.execute(select(PolicyChunkModel).where(PolicyChunkModel.clause_id == "POL-WARRANTY-01"))).scalar_one()
    assert row.status == "retired"
    # and it comes back when the document does
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Bảo hành mười hai tháng.")
    assert (await sync_policies(session, docs_dir=tmp_path)).updated == ["POL-WARRANTY-01@2026-11-01"]


async def test_an_invalid_corpus_is_refused_before_anything_is_written(session: AsyncSession, tmp_path: Path) -> None:
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Xem thêm POL-GHOST-99.")
    with pytest.raises(PolicyDocumentError):
        await sync_policies(session, docs_dir=tmp_path)
    assert (await session.execute(select(PolicyChunkModel))).first() is None


# --- retrieval sees changes without a manual cache clear ----------------------------------------------
async def test_retrieval_follows_additions_edits_and_retirements(session: AsyncSession, tmp_path: Path) -> None:
    retriever = PolicyRetriever(session=session)
    await sync_policies(session, docs_dir=tmp_path)
    assert "POL-WARRANTY-01" not in [r["clause_id"] for r in await retriever.retrieve("bảo hành tai nghe mấy tháng")]

    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Tai nghe được bảo hành mười hai tháng kể từ ngày mua.")
    await sync_policies(session, docs_dir=tmp_path)
    assert [r["clause_id"] for r in await retriever.retrieve("bảo hành tai nghe mấy tháng", top_k=1)] == ["POL-WARRANTY-01"]

    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Tai nghe được bảo hành hai mươi bốn tháng kể từ ngày mua.")
    await sync_policies(session, docs_dir=tmp_path)
    top = (await retriever.retrieve("bảo hành tai nghe mấy tháng", top_k=1))[0]
    assert "hai mươi bốn" in top["text"]

    (tmp_path / "w.md").unlink()
    await sync_policies(session, docs_dir=tmp_path)
    assert "POL-WARRANTY-01" not in [r["clause_id"] for r in await retriever.retrieve("bảo hành tai nghe mấy tháng")]


async def test_a_document_marked_retired_is_not_retrieved(session: AsyncSession, tmp_path: Path) -> None:
    write_doc(tmp_path, "w.md", "POL-WARRANTY-01", "Tai nghe được bảo hành mười hai tháng.", status="retired")
    await sync_policies(session, docs_dir=tmp_path)
    assert "POL-WARRANTY-01" not in [r["clause_id"] for r in await PolicyRetriever(session=session).retrieve("bảo hành tai nghe")]


# --- the first stage is replaceable -------------------------------------------------------------------
async def test_the_candidate_source_can_be_replaced() -> None:
    class Fixed:
        def candidates(self, snapshot, chunks, query):  # type: ignore[no-untyped-def]
            picked = [c for c in chunks if c["clause_id"] == "POL-SHIP-01"]
            return [{**c, "score": 1.0} for c in picked]

    results = await PolicyRetriever(in_memory=True, candidates=Fixed()).retrieve("bất kỳ câu hỏi nào")
    assert [r["clause_id"] for r in results] == ["POL-SHIP-01"]


# --- result budget ------------------------------------------------------------------------------------
def test_results_beyond_the_budget_are_dropped_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shopagent.agent.tools.definitions.get_app_config", lambda: {"retrieval": {"max_result_chars": 100}})
    matches = [{"clause_id": f"C{i}", "text": "x" * 60} for i in range(4)]
    assert [m["clause_id"] for m in _within_budget(matches)] == ["C0"]
    assert [m["clause_id"] for m in _within_budget([{"clause_id": "BIG", "text": "y" * 500}, *matches])] == ["BIG"]
    monkeypatch.setattr("shopagent.agent.tools.definitions.get_app_config", lambda: {"retrieval": {"max_result_chars": 130}})
    assert [m["clause_id"] for m in _within_budget(matches)] == ["C0", "C1"]
