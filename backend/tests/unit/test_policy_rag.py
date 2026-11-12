"""Unit and benchmark tests for Policy RAG and Hybrid Retrieval."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from shopagent.core.config import get_rules_config
from shopagent.rag.chunker import remove_vietnamese_accents
from shopagent.rag.generator import _CLAUSE_TEMPLATES, generate_policy_clauses
from shopagent.rag.retriever import HybridRetriever


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
    assert f"{rules['return']['return_shipping']['customer_fee_vnd']}" in by_id["POL-RETURN-02"]
    # Check auto approve refund limit from rules
    assert f"{rules['refund']['auto_approve_max_vnd']}" in by_id["POL-REFUND-02"]


def test_vietnamese_unaccent_normalization():
    """Verify Vietnamese accents are correctly stripped for robust search."""
    assert remove_vietnamese_accents("Đổi trả hàng lỗi") == "doi tra hang loi"
    assert remove_vietnamese_accents("Thời gian hoàn tiền ví điện tử") == "thoi gian hoan tien vi dien tu"
    assert remove_vietnamese_accents("Áo phông Đen") == "ao phong den"


@pytest.mark.asyncio
async def test_policy_retrieval_benchmark_r1_and_r2():
    """Evaluate 80 queries benchmark: R1 (Recall@4 >= 95%) and R2 (Recall@4 >= 90%)."""
    queries_path = Path(__file__).resolve().parents[3] / "evals" / "retrieval" / "queries.yaml"
    assert queries_path.exists(), f"Query benchmark file not found at {queries_path}"

    with open(queries_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    standard_queries = data.get("standard", [])
    unaccented_queries = data.get("unaccented_and_abbreviated", [])

    assert len(standard_queries) == 40
    assert len(unaccented_queries) == 40

    retriever = HybridRetriever(session=None)  # Uses in-memory generator cache

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
    assert r2_recall >= 0.90, f"R2 unaccented recall@4 is {r2_recall*100:.1f}%, expected >= 90%"


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
        db_retriever = HybridRetriever(session=session)
        results = await db_retriever.retrieve("mình muốn trả hàng đổi ý mất phí bao nhiêu", top_k=2)
        assert len(results) > 0
        clause_ids = [r["clause_id"] for r in results]
        assert "POL-RETURN-02" in clause_ids

    await engine.dispose()
