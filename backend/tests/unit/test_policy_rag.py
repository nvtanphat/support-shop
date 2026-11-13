"""Unit and benchmark tests for Policy RAG and Hybrid Retrieval."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from shopagent.core.config import get_rules_config
from shopagent.rag.chunker import remove_vietnamese_accents
from shopagent.rag.generator import _CLAUSE_TEMPLATES, generate_policy_clauses
from shopagent.rag.retriever import PolicyRetriever


def test_no_hardcoded_policy_numbers_in_templates():
    """Quality Gate Giai đoạn 4: Không có con số viết tay trong mẫu chính sách."""
    for item in _CLAUSE_TEMPLATES:
        tmpl = item["template"]
        # Match standalone numbers not enclosed in jinja tags {{ ... }}
        non_jinja_segments = re.split(r"\{\{.*?\}\}", tmpl)
        for seg in non_jinja_segments:
            # Check for numbers like 15, 7, 30000, 500000, 2000000
            numbers = re.findall(r"\b\d{2,}\b", seg)
            assert len(numbers) == 0, (
                f"Phát hiện số viết tay '{numbers}' trong mẫu {item['clause_id']}: '{seg}'"
            )


def test_clause_generation_dynamic_from_rules():
    """Verify generated clauses dynamically take values from rules.yaml."""
    rules = get_rules_config()
    clauses = generate_policy_clauses(rules)
    assert len(clauses) >= 8

    by_id = {c["clause_id"]: c["text"] for c in clauses}
    # Check return window 15 days from rules
    assert f"{rules['return']['windows_days']['defect_like']} ngày" in by_id["POL-RETURN-01"]
    # Check change of mind fee from rules
    def vnd(amount: int) -> str:
        return f"{amount:,}".replace(",", ".") + " đ"

    assert vnd(rules['return']['return_shipping']['customer_fee_vnd']) in by_id["POL-RETURN-02"]
    # Check auto approve refund limit from rules
    assert vnd(rules['refund']['auto_approve_max_vnd']) in by_id["POL-REFUND-02"]
    # Customer-facing text must not leak configuration tokens
    assert all("end_of_local_day" not in text for text in by_id.values())


def test_vietnamese_unaccent_normalization():
    """Verify Vietnamese accents are correctly stripped for robust search."""
    assert remove_vietnamese_accents("Đổi trả hàng lỗi") == "doi tra hang loi"
    assert remove_vietnamese_accents("Thời gian hoàn tiền ví điện tử") == "thoi gian hoan tien vi dien tu"
    assert remove_vietnamese_accents("Áo phông Đen") == "ao phong den"


@pytest.mark.asyncio
async def test_policy_retrieval_benchmark_r1_and_r2():
    """Evaluate 80 queries benchmark: R1 (Recall@4 >= 95%) and R2 (Recall@4 >= 90%)."""
    queries_path = Path(__file__).resolve().parents[3] / "evals" / "retrieval" / "policy_queries_baseline.yaml"
    assert queries_path.exists(), f"Query benchmark file not found at {queries_path}"

    with open(queries_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    standard_queries = data.get("standard", [])
    unaccented_queries = data.get("unaccented_and_abbreviated", [])

    assert len(standard_queries) == 40
    assert len(unaccented_queries) == 40

    retriever = PolicyRetriever(in_memory=True)  # Uses in-memory generator cache

    # Benchmark Standard Queries (R1)
    std_hits = 0
    for q_item in standard_queries:
        query = q_item["query"]
        expected = q_item["expected_clause"]
        results = await retriever.retrieve(query=query, top_k=4)
        retrieved_ids = [r["clause_id"] for r in results]
        if expected in retrieved_ids:
            std_hits += 1

    r1_recall = std_hits / len(standard_queries)

    # Benchmark Unaccented / Abbreviated Queries (R2)
    unacc_hits = 0
    for q_item in unaccented_queries:
        query = q_item["query"]
        expected = q_item["expected_clause"]
        results = await retriever.retrieve(query=query, top_k=4)
        retrieved_ids = [r["clause_id"] for r in results]
        if expected in retrieved_ids:
            unacc_hits += 1

    r2_recall = unacc_hits / len(unaccented_queries)

    # Section 14.6 Quality Gates: R1 >= 95%, R2 >= 90%
    assert r1_recall >= 0.95, f"R1 standard recall@4 is {r1_recall*100:.1f}%, expected >= 95%"
    assert r2_recall >= 0.95, f"R2 unaccented recall@4 is {r2_recall*100:.1f}%, expected >= 95%"


@pytest.mark.asyncio
async def test_policy_indexing_and_db_retrieval():
    """Verify end-to-end indexing into database and retrieval from DB."""
    from shopagent.infra.db.tables import Base
    from shopagent.rag.indexer import index_policies
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        # Index into DB
        saved = await index_policies(session)
        assert len(saved) >= 8

        # Retrieve using DB session
        db_retriever = PolicyRetriever(session=session)
        results = await db_retriever.retrieve("mình muốn trả hàng đổi ý mất phí bao nhiêu", top_k=2)
        assert len(results) > 0
        clause_ids = [r["clause_id"] for r in results]
        assert "POL-RETURN-02" in clause_ids

    await engine.dispose()


@pytest.mark.asyncio
async def test_retriever_raises_on_db_failure():
    """Verify that DB failures are never swallowed silently with except Exception: pass."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy.exc import OperationalError

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=OperationalError("DB connection failed", None, None))

    retriever = PolicyRetriever(session=mock_session)
    with pytest.raises(OperationalError):
        await retriever.retrieve("đổi trả hàng lỗi", top_k=2)


@pytest.mark.asyncio
async def test_retriever_returns_empty_when_no_relevant_evidence():
    """Verify retriever returns empty list when query has no relevant policy match."""
    retriever = PolicyRetriever(in_memory=True)
    results = await retriever.retrieve("zzzxxyyyy qwerty asdfghjkl random string without any sense", top_k=2)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_retriever_provenance_and_version():
    """Verify retrieved results retain policy version and provenance metadata."""
    retriever = PolicyRetriever(in_memory=True)
    results = await retriever.retrieve("chính sách hoàn tiền ví điện tử", top_k=1)
    assert len(results) > 0
    first = results[0]
    assert "version" in first
    assert "score" in first
    assert "clause_id" in first
    assert first["version"] == "2026-11-01"



# ---------------------------------------------------------------------------
# search_policy tool: failure modes are distinct and never fall back silently
# ---------------------------------------------------------------------------
async def _policy_tool(session):  # type: ignore[no-untyped-def]
    import uuid

    from shopagent.agent.tools.definitions import create_tools
    from shopagent.core.principal import Principal

    tools = create_tools(session, Principal.guest(), uuid.uuid4(), retrieved_clauses=[])
    return next(t for t in tools if t.name == "search_policy")


async def _memory_session():  # type: ignore[no-untyped-def]
    from shopagent.infra.db.tables import Base
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def test_retriever_requires_explicit_offline_mode() -> None:
    with pytest.raises(ValueError):
        PolicyRetriever()


@pytest.mark.asyncio
async def test_search_policy_reports_empty_index_instead_of_no_evidence() -> None:
    engine, factory = await _memory_session()
    async with factory() as session:
        tool = await _policy_tool(session)
        result = await tool.ainvoke({"query": "đổi trả hàng lỗi"})
    await engine.dispose()
    assert result["status"] == "index_unavailable"
    assert result["results"] == []


@pytest.mark.asyncio
async def test_search_policy_reports_database_failure() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy.exc import OperationalError

    session = MagicMock()
    session.execute = AsyncMock(side_effect=OperationalError("down", None, None))
    tool = await _policy_tool(session)
    result = await tool.ainvoke({"query": "đổi trả hàng lỗi"})
    assert result["status"] == "db_error"
    assert result["results"] == []


@pytest.mark.asyncio
async def test_search_policy_rejects_invalid_as_of_instead_of_ignoring_it() -> None:
    engine, factory = await _memory_session()
    async with factory() as session:
        tool = await _policy_tool(session)
        result = await tool.ainvoke({"query": "đổi trả hàng lỗi", "as_of": "hôm qua"})
    await engine.dispose()
    assert result["error_code"] == "INVALID_AS_OF"


@pytest.mark.asyncio
async def test_search_policy_returns_provenance_and_only_effective_clauses() -> None:
    from datetime import UTC, datetime

    from shopagent.infra.db.tables import PolicyChunkModel
    from shopagent.rag.indexer import index_policies
    from sqlalchemy import update

    engine, factory = await _memory_session()
    async with factory() as session:
        await index_policies(session)
        tool = await _policy_tool(session)
        current = await tool.ainvoke({"query": "đổi ý trả hàng mất phí bao nhiêu"})
        assert current["status"] == "success"
        assert current["policy_versions"] == ["2026-11-01"]
        first = current["results"][0]
        assert first["version"] and first["effective_from"] and "effective_to" in first

        # Expire every clause in the past: today's question must find nothing effective.
        await session.execute(update(PolicyChunkModel).values(effective_to=datetime(2026, 1, 1, tzinfo=UTC)))
        await session.commit()
        expired = await tool.ainvoke({"query": "đổi ý trả hàng mất phí bao nhiêu"})
    await engine.dispose()
    assert expired["status"] == "no_evidence"


# ---------------------------------------------------------------------------
# Optional reranking: reorders candidates, and a broken reranker is an error, not a fallback
# ---------------------------------------------------------------------------
class PreferClause:
    """Stub cross-encoder that scores one clause above all others."""

    def __init__(self, clause_text_marker: str) -> None:
        self.marker = clause_text_marker

    def scores(self, query, texts):  # type: ignore[no-untyped-def]
        return [10.0 if self.marker in t else 0.0 for t in texts]


@pytest.mark.asyncio
async def test_reranker_reorders_candidates_and_keeps_provenance() -> None:
    plain = PolicyRetriever(in_memory=True)
    before = await plain.retrieve("đổi trả hàng", top_k=4)
    assert before[0]["clause_id"] != "POL-REFUND-02"

    reranked = PolicyRetriever(in_memory=True, reranker=PreferClause("Hạn mức duyệt"))
    after = await reranked.retrieve("đổi trả hàng", top_k=4)
    assert after[0]["clause_id"] == "POL-REFUND-02"
    assert after[0]["version"] and "effective_from" in after[0]


@pytest.mark.asyncio
async def test_enabled_but_missing_reranker_is_an_explicit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from shopagent.rag import reranker as reranker_module

    def broken(model_name: str):  # type: ignore[no-untyped-def]
        raise reranker_module.RerankerUnavailableError("model missing")

    monkeypatch.setattr(reranker_module, "get_app_config", lambda: {"retrieval": {"reranker": {"enabled": True, "model": "x"}}})
    monkeypatch.setattr(reranker_module, "CrossEncoderReranker", broken)
    monkeypatch.setattr(reranker_module, "_cached", None)
    monkeypatch.setattr(reranker_module, "get_settings", lambda: type("S", (), {"RETRIEVAL_RERANKER_ENABLED": None})())
    with pytest.raises(reranker_module.RerankerUnavailableError):
        await PolicyRetriever(in_memory=True).retrieve("đổi trả hàng", top_k=2)


# ---------------------------------------------------------------------------
# Index snapshot and rerank caches
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_index_snapshot_is_reused_and_invalidated_when_clauses_expire() -> None:
    from datetime import UTC, datetime

    from shopagent.infra.db.tables import PolicyChunkModel
    from shopagent.rag import retriever as retriever_module
    from shopagent.rag.indexer import index_policies
    from sqlalchemy import event, update

    retriever_module.clear_retrieval_caches()
    engine, factory = await _memory_session()
    async with factory() as session:
        await index_policies(session)
        full_loads: list[str] = []

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def count_full_loads(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
            if "policy_chunks.text" in statement:
                full_loads.append(statement)

        retriever = PolicyRetriever(session=session)
        for _ in range(3):
            assert await retriever.retrieve("đổi ý trả hàng mất phí bao nhiêu")
        assert len(full_loads) == 1  # one load, two cache hits

        await session.execute(update(PolicyChunkModel).values(effective_to=datetime(2026, 1, 1, tzinfo=UTC)))
        await session.commit()
        assert await retriever.retrieve("đổi ý trả hàng mất phí bao nhiêu") == []  # fingerprint changed
        assert len(full_loads) == 2
    await engine.dispose()
    retriever_module.clear_retrieval_caches()


@pytest.mark.asyncio
async def test_rerank_results_are_cached_per_query() -> None:
    from shopagent.rag import retriever as retriever_module

    class CountingReranker:
        calls = 0

        def scores(self, query, texts):  # type: ignore[no-untyped-def]
            CountingReranker.calls += 1
            return [float(len(t)) for t in texts]

    retriever_module.clear_retrieval_caches()
    retriever = PolicyRetriever(in_memory=True, reranker=CountingReranker())
    first = await retriever.retrieve("đổi trả hàng", top_k=3)
    second = await retriever.retrieve("đổi trả hàng", top_k=3)
    assert first == second and CountingReranker.calls == 1
    retriever_module.clear_retrieval_caches()


def test_query_normalization_expands_shorthand_without_touching_words() -> None:
    from shopagent.rag.lexical import normalize_query

    assert normalize_query("áo chật đổi sz dc ko") == "áo chật đổi size duoc khong"
    assert "500000" in normalize_query("hoàn trên 500k")
    assert "2000000" in normalize_query("trên 2 triệu thì ai duyệt")
    assert normalize_query("kho hàng") == "kho hàng"  # 'k' alone is shorthand, 'kho' is a word


@pytest.mark.asyncio
async def test_production_retriever_meets_the_measured_benchmark_floor() -> None:
    """The production path (not only the research runner) keeps the benchmark gains."""
    spec = yaml.safe_load((Path(__file__).resolve().parents[3] / "evals" / "retrieval" / "policy_queries_independent.yaml").read_text(encoding="utf-8"))
    items = [i for i in spec["queries"] if i["split"] == "test" and i["expected"] and "as_of" not in i]
    retriever = PolicyRetriever(in_memory=True)
    top1 = top4 = 0
    for item in items:
        got = [r["clause_id"] for r in await retriever.retrieve(item["q"], top_k=4)]
        top1 += bool(got) and got[0] in item["expected"]
        top4 += all(c in got for c in item["expected"])
    assert top4 / len(items) >= 0.95
    assert top1 / len(items) >= 0.60


# ---------------------------------------------------------------------------
# Unsupported-question threshold and diacritic restoration
# ---------------------------------------------------------------------------
class FixedScores:
    """Stub cross-encoder returning one score for every clause, and remembering what it was asked."""

    def __init__(self, score: float) -> None:
        self.score = score
        self.queries: list[str] = []

    def scores(self, query, texts):  # type: ignore[no-untyped-def]
        self.queries.append(query)
        return [self.score] * len(texts)


@pytest.mark.asyncio
async def test_question_below_the_score_threshold_returns_no_evidence() -> None:
    weak = PolicyRetriever(in_memory=True, reranker=FixedScores(-9.0), min_rerank_score=-4.76)
    assert await weak.retrieve("đổi trả hàng lỗi", top_k=4) == []
    strong = PolicyRetriever(in_memory=True, reranker=FixedScores(3.0), min_rerank_score=-4.76)
    assert await strong.retrieve("đổi trả hàng lỗi", top_k=4)
    unguarded = PolicyRetriever(in_memory=True, reranker=FixedScores(-9.0), min_rerank_score=None)
    assert await unguarded.retrieve("đổi trả hàng lỗi", top_k=4)  # no threshold configured: never rejects


@pytest.mark.asyncio
async def test_cross_encoder_reads_the_query_with_diacritics_restored() -> None:
    stub = FixedScores(1.0)
    retriever = PolicyRetriever(in_memory=True, reranker=stub)
    await retriever.retrieve("hang loi toi muon doi tra", top_k=2)
    assert "hàng" in stub.queries[0] and "tôi" in stub.queries[0] and "muốn" in stub.queries[0]
    await retriever.retrieve("Đơn đã giao rồi, mình hủy được không?", top_k=2)
    assert stub.queries[1] == "đơn đã giao rồi mình hủy được không"  # already accented: normalised, never rewritten


def test_diacritic_restoration_uses_the_policy_vocabulary_and_function_words() -> None:
    from shopagent.rag.diacritics import build_restorer

    restore = build_restorer(["Thời hạn đổi trả hàng lỗi trong vòng 15 ngày", "Tối đa 5 ngày"])
    assert restore("toi muon doi tra hang") == "tôi muốn đổi trả hàng"  # 'tôi' beats the corpus word 'tối'
    assert restore("thoi han 15 ngay") == "thời hạn 15 ngày"
    assert restore("Đổi trả") == "Đổi trả"  # accented input is left alone
    assert restore("zzz qwerty") == "zzz qwerty"  # unknown words pass through


def test_warm_up_loads_the_reranker_only_when_enabled_and_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    from shopagent.rag import reranker as reranker_module

    monkeypatch.setattr(reranker_module, "_cached", None)
    monkeypatch.setattr(reranker_module, "get_settings", lambda: type("S", (), {"RETRIEVAL_RERANKER_ENABLED": False})())
    assert reranker_module.warm_up() is False  # disabled: nothing is loaded

    def broken(model_name: str):  # type: ignore[no-untyped-def]
        raise reranker_module.RerankerUnavailableError("model missing")

    monkeypatch.setattr(reranker_module, "get_settings", lambda: type("S", (), {"RETRIEVAL_RERANKER_ENABLED": True})())
    monkeypatch.setattr(reranker_module, "get_app_config", lambda: {"retrieval": {"reranker": {"enabled": True, "model": "x"}}})
    monkeypatch.setattr(reranker_module, "CrossEncoderReranker", broken)
    with pytest.raises(reranker_module.RerankerUnavailableError):
        reranker_module.warm_up()
