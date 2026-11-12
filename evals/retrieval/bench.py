"""Retrieval benchmark: compare ranking strategies on benchmark_v2.yaml.

Strategies share the temporal filter and the chunk store, so differences come from ranking only.
The unsupported-query threshold is calibrated on the `dev` split and every reported number comes
from the held-out `test` split.

    uv run python -m evals.retrieval.bench [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import math
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from shopagent.rag.chunker import build_chunks_from_clauses, tokenize_unaccent
from shopagent.rag.embeddings import get_embedding_provider
from shopagent.rag.generator import generate_policy_clauses

BENCHMARK_PATH = Path(__file__).with_name("benchmark_v2.yaml")
TOP_K = 4
RRF_K = 60


@dataclass(frozen=True)
class Ranking:
    clause_ids: list[str]
    versions: list[str]
    confidence: float  # higher = more likely the index can answer; used for rejection


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def build_chunks(extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clauses = generate_policy_clauses() + extra
    chunks = build_chunks_from_clauses(clauses)
    embedder = get_embedding_provider()
    for chunk, emb in zip(chunks, embedder.embed_documents([c["text"] for c in chunks]), strict=True):
        chunk["embedding"] = emb
        chunk["from"] = _parse_time(chunk.get("effective_from"))
        chunk["to"] = _parse_time(chunk.get("effective_to"))
    return chunks


def effective_at(chunks: list[dict[str, Any]], as_of: datetime | None) -> list[dict[str, Any]]:
    if as_of is None:
        return [c for c in chunks if c["to"] is None]
    return [c for c in chunks if (c["from"] is None or c["from"] <= as_of) and (c["to"] is None or as_of < c["to"])]


class Bm25Index:
    """Okapi BM25 over accent-stripped tokens (k1=1.5, b=0.75)."""

    def __init__(self, chunks: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [tokenize_unaccent(c["text"]) for c in chunks]
        self.avg_len = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df: dict[str, int] = {}
        for doc in self.docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize_unaccent(query)
        out = []
        for doc in self.docs:
            length = len(doc)
            total = 0.0
            for term in terms:
                tf = doc.count(term)
                if tf and term in self.idf:
                    total += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            out.append(total)
        return out

    def max_possible(self, query: str) -> float:
        return sum(self.idf.get(t, 0.0) for t in set(tokenize_unaccent(query))) or 1.0


def _rank(scores: list[float]) -> list[int]:
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)


def _rrf(*score_lists: list[float]) -> list[float]:
    fused = [0.0] * len(score_lists[0])
    for scores in score_lists:
        for rank, idx in enumerate(_rank(scores)):
            fused[idx] += 1.0 / (RRF_K + rank)
    return fused


def _ranking(chunks: list[dict[str, Any]], order: list[int], confidence: float) -> Ranking:
    picked = order[:TOP_K]
    return Ranking([chunks[i]["clause_id"] for i in picked], [chunks[i]["version"] for i in picked], confidence)


def strategy_current(chunks: list[dict[str, Any]], query: str) -> Ranking:
    """The production algorithm: token-overlap count + hashed n-gram cosine, fused with RRF."""
    q_tokens = set(tokenize_unaccent(query))
    q_emb = get_embedding_provider().embed_query(query)
    overlap = [float(len(q_tokens & set(c["tokens"]))) for c in chunks]
    cosine = [max(0.0, sum(a * b for a, b in zip(q_emb, c["embedding"], strict=False))) for c in chunks]
    top = max(overlap) if overlap else 0.0
    order = _rank(_rrf(overlap, cosine))
    return _ranking(chunks, order, top)


def strategy_bm25(chunks: list[dict[str, Any]], query: str, index: Bm25Index) -> Ranking:
    scores = index.scores(query)
    return _ranking(chunks, _rank(scores), max(scores) / index.max_possible(query))


def strategy_bm25_hybrid(chunks: list[dict[str, Any]], query: str, index: Bm25Index) -> Ranking:
    scores = index.scores(query)
    q_emb = get_embedding_provider().embed_query(query)
    cosine = [max(0.0, sum(a * b for a, b in zip(q_emb, c["embedding"], strict=False))) for c in chunks]
    return _ranking(chunks, _rank(_rrf(scores, cosine)), max(scores) / index.max_possible(query))


class SemanticModel:
    """Optional multilingual sentence embeddings through ONNX (fastembed); not a project dependency."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self.name = model_name
        self.model = TextEmbedding(model_name=model_name)
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(texts)]

    def embed_query(self, query: str) -> list[float]:
        if query not in self._cache:
            self._cache[query] = self.embed([query])[0]
        return self._cache[query]


class Reranker:
    """Optional multilingual cross-encoder (fastembed ONNX); scores every (query, clause) pair."""

    def __init__(self, model_name: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = model_name
        self.model = TextCrossEncoder(model_name=model_name)

    def scores(self, query: str, texts: list[str]) -> list[float]:
        return [float(x) for x in self.model.rerank(query, texts)]


def strategy_rerank(chunks: list[dict[str, Any]], query: str, reranker: Reranker) -> Ranking:
    scores = reranker.scores(query, [c["text"] for c in chunks])
    return _ranking(chunks, _rank(scores), max(scores))


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


def strategy_semantic(chunks: list[dict[str, Any]], query: str, model: SemanticModel) -> Ranking:
    q = model.embed_query(query)
    sims = [_cos(q, c["sem"]) for c in chunks]
    return _ranking(chunks, _rank(sims), max(sims))


def strategy_semantic_bm25(chunks: list[dict[str, Any]], query: str, index: Bm25Index, model: SemanticModel) -> Ranking:
    q = model.embed_query(query)
    sims = [_cos(q, c["sem"]) for c in chunks]
    fused = _rrf(index.scores(query), sims)
    return _ranking(chunks, _rank(fused), max(sims))


def metrics_for(item: dict[str, Any], ranking: Ranking) -> dict[str, float]:
    expected = item["expected"]
    hits = [1 if cid in expected else 0 for cid in ranking.clause_ids]
    recall_at_1 = float(bool(expected) and ranking.clause_ids[:1] and ranking.clause_ids[0] in expected)
    found_at_4 = len({c for c in ranking.clause_ids if c in expected})
    first = next((i + 1 for i, h in enumerate(hits) if h), None)
    dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(expected), TOP_K)))
    version_ok = 1.0
    if "expected_version" in item:
        top = next((v for c, v in zip(ranking.clause_ids, ranking.versions, strict=True) if c in expected), None)
        version_ok = float(top == item["expected_version"])
    return {
        "recall@1": recall_at_1,
        "recall@4": found_at_4 / len(expected),
        "mrr": 0.0 if first is None else 1.0 / first,
        "ndcg@4": dcg / ideal if ideal else 0.0,
        "precision@4": sum(hits) / TOP_K,
        "version_ok": version_ok,
    }


def calibrate_threshold(dev: list[tuple[dict[str, Any], Ranking]]) -> float:
    """Lowest threshold that keeps >= 95% of answerable dev queries; maximises dev rejection."""
    answerable = sorted(r.confidence for item, r in dev if item["expected"])
    keep_index = int(len(answerable) * 0.05)
    return answerable[keep_index] if answerable else 0.0


def evaluate(name: str, run: Callable[[dict[str, Any]], Ranking], items: list[dict[str, Any]]) -> dict[str, Any]:
    latencies: list[float] = []
    scored: list[tuple[dict[str, Any], Ranking]] = []
    for item in items:
        started = time.perf_counter()
        ranking = run(item)
        latencies.append((time.perf_counter() - started) * 1000)
        scored.append((item, ranking))
    dev = [(i, r) for i, r in scored if i["split"] == "dev"]
    test = [(i, r) for i, r in scored if i["split"] == "test"]
    threshold = calibrate_threshold(dev)

    answerable = [(i, r) for i, r in test if i["expected"]]
    ood = [(i, r) for i, r in test if not i["expected"]]
    agg: dict[str, float] = {}
    per_metric = [metrics_for(i, r) for i, r in answerable]
    for key in per_metric[0]:
        agg[key] = sum(m[key] for m in per_metric) / len(per_metric)
    by_kind: dict[str, float] = {}
    for kind in sorted({i["kind"] for i, _ in answerable}):
        rows = [metrics_for(i, r)["recall@4"] for i, r in answerable if i["kind"] == kind]
        by_kind[kind] = sum(rows) / len(rows)
    return {
        "strategy": name,
        "test_answerable": len(answerable),
        "test_out_of_domain": len(ood),
        **{k: round(v, 3) for k, v in agg.items()},
        "recall@4_by_kind": {k: round(v, 3) for k, v in by_kind.items()},
        "unsupported_rejection": round(sum(r.confidence < threshold for _, r in ood) / len(ood), 3),
        "false_rejection": round(sum(r.confidence < threshold for _, r in answerable) / len(answerable), 3),
        "rejection_threshold": round(threshold, 4),
        "latency_ms_p50": round(sorted(latencies)[len(latencies) // 2], 3),
    }


def run_benchmark(semantic_model: str | None = None, reranker_model: str | None = None) -> list[dict[str, Any]]:
    spec = yaml.safe_load(BENCHMARK_PATH.read_text(encoding="utf-8"))
    items = spec["queries"]
    tracemalloc.start()
    chunks = build_chunks(spec["temporal_clauses"])
    bm25_all = Bm25Index(chunks)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    def visible(item: dict[str, Any]) -> list[dict[str, Any]]:
        return effective_at(chunks, _parse_time(item.get("as_of")) or datetime.fromisoformat("2026-11-12T10:00:00+07:00"))

    def with_index(fn: Callable[..., Ranking]) -> Callable[[dict[str, Any]], Ranking]:
        def run(item: dict[str, Any]) -> Ranking:
            pool = visible(item)
            return fn(pool, item["q"], Bm25Index(pool)) if pool else Ranking([], [], 0.0)

        return run

    semantic: SemanticModel | None = None
    if semantic_model:
        semantic = SemanticModel(semantic_model)
        for chunk, vec in zip(chunks, semantic.embed([c["text"] for c in chunks]), strict=True):
            chunk["sem"] = vec

    results = [
        evaluate("current (overlap + hashed n-gram, RRF)", lambda it: strategy_current(visible(it), it["q"]), items),
        evaluate("bm25", with_index(strategy_bm25), items),
        evaluate("bm25 + hashed n-gram, RRF", with_index(strategy_bm25_hybrid), items),
    ]
    if semantic is not None:
        sem = semantic
        results.append(evaluate(f"semantic {sem.name}", lambda it: strategy_semantic(visible(it), it["q"], sem), items))
        results.append(
            evaluate(
                f"bm25 + semantic {sem.name}, RRF",
                lambda it: strategy_semantic_bm25(visible(it), it["q"], Bm25Index(visible(it)), sem),
                items,
            )
        )
    if reranker_model:
        rr = Reranker(reranker_model)
        results.append(evaluate(f"rerank all clauses with {rr.name}", lambda it: strategy_rerank(visible(it), it["q"], rr), items))
    for row in results:
        row["index_build_peak_kib"] = round(peak / 1024, 1)
    _ = bm25_all
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--semantic-model", default=None, help="fastembed model id, e.g. sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--reranker-model", default=None, help="fastembed cross-encoder id, e.g. BAAI/bge-reranker-v2-m3-int8")
    args = parser.parse_args()
    results = run_benchmark(args.semantic_model, args.reranker_model)
    for row in results:
        print(json.dumps(row, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
