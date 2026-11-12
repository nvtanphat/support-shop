"""The independent retrieval benchmark is well-formed and its baseline is reproducible.

These tests pin the measured baseline so a retrieval change cannot silently make it worse; they do
not claim the acceptance thresholds are met (see docs/eval-report.md).
"""

from __future__ import annotations

import yaml

from evals.retrieval.bench import BENCHMARK_PATH, build_chunks, run_benchmark


def load_spec() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(BENCHMARK_PATH.read_text(encoding="utf-8"))


def test_benchmark_covers_required_query_kinds_and_both_splits() -> None:
    items = load_spec()["queries"]
    kinds = {i["kind"] for i in items}
    assert {"paraphrase", "slang", "typo", "unaccented", "multi_intent", "out_of_domain", "temporal"} <= kinds
    assert {i["split"] for i in items} == {"dev", "test"}
    assert len({i["id"] for i in items}) == len(items)


def test_every_expected_clause_exists_in_the_index() -> None:
    spec = load_spec()
    known = {c["clause_id"] for c in build_chunks(spec["temporal_clauses"])}
    for item in spec["queries"]:
        assert set(item["expected"]) <= known, item["id"]
        assert (not item["expected"]) == (item["kind"] == "out_of_domain"), item["id"]


def test_expired_policy_version_is_selected_by_as_of() -> None:
    rows = {r["strategy"]: r for r in run_benchmark()}
    assert all(r["version_ok"] == 1.0 for r in rows.values())


def test_measured_baseline_does_not_regress() -> None:
    rows = {r["strategy"]: r for r in run_benchmark()}
    # "bm25 + query normalization" is the production ranking; the legacy row is kept only as a baseline.
    production = rows["bm25 + query normalization"]
    legacy = rows["current (overlap + hashed n-gram, RRF)"]
    assert production["recall@4"] >= 0.95 and production["recall@1"] >= 0.65
    assert production["mrr"] > legacy["mrr"] and production["ndcg@4"] > legacy["ndcg@4"]
    current = production
    assert current["test_answerable"] >= 30 and current["test_out_of_domain"] >= 10
