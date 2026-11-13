"""The retrieval benchmark files stay well-formed and keep covering the corpus as it grows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from shopagent.rag.indexer import build_corpus

_DIR = Path("evals/retrieval")
_FILES = ["policy_queries_independent.yaml", "policy_queries_holdout.yaml"]
_KINDS = {"paraphrase", "slang", "typo", "unaccented", "multi_intent", "temporal", "out_of_domain"}
_NEAR_TOPIC_SHARE = 0.2


def _queries(name: str) -> list[dict]:  # type: ignore[type-arg]
    return list(yaml.safe_load((_DIR / name).read_text(encoding="utf-8"))["queries"])


@pytest.mark.parametrize("name", _FILES)
def test_queries_are_well_formed(name: str) -> None:
    clause_ids = {c["clause_id"] for c in build_corpus()}
    seen: set[str] = set()
    for q in _queries(name):
        assert q["id"] not in seen, f"{name}: duplicate id {q['id']}"
        seen.add(q["id"])
        assert q["kind"] in _KINDS, f"{q['id']}: unknown kind {q['kind']}"
        assert q["q"].strip(), f"{q['id']}: empty question"
        assert (q["kind"] == "out_of_domain") == (not q["expected"]), f"{q['id']}: only out_of_domain queries have no expected clause"
        # Temporal queries may expect superseded clause ids that live in temporal_clauses, not in the corpus.
        if q["kind"] != "temporal":
            unknown = set(q["expected"]) - clause_ids
            assert not unknown, f"{q['id']} expects {unknown}, which are not in the corpus"
        assert q.get("near_topic") is None or q["kind"] == "out_of_domain", f"{q['id']}: near_topic only applies to out_of_domain"


def test_every_active_clause_is_asked_about_by_at_least_one_query() -> None:
    expected = {c for name in _FILES for q in _queries(name) for c in q["expected"]}
    uncovered = sorted(c["clause_id"] for c in build_corpus() if c.get("status", "active") == "active" and c["clause_id"] not in expected)
    assert not uncovered, f"No benchmark query expects {uncovered}: add queries before relying on retrieval for them"


@pytest.mark.parametrize("name", _FILES[:1])
def test_enough_out_of_domain_queries_are_close_to_the_policy_topic(name: str) -> None:
    out = [q for q in _queries(name) if q["kind"] == "out_of_domain"]
    near = [q for q in out if q.get("near_topic")]
    assert len(near) / len(out) >= _NEAR_TOPIC_SHARE, f"{len(near)}/{len(out)} near-topic: easy rejections prove nothing about the threshold"
