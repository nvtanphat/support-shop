"""Calibrate the unsupported-query threshold on the independent query set, then report on the untouched holdout query set.

    uv run --extra rerank python -m evals.retrieval.holdout [--json out.json]

The production retriever runs unchanged (BM25, normalised query, diacritic restoration, cross-encoder).
The threshold is the score that maximises balanced accuracy on the independent query set; the holdout set was written
afterwards and is only ever scored with that frozen threshold.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
from typing import Any

import yaml
from shopagent.rag import retriever as retriever_module
from shopagent.rag.reranker import CrossEncoderReranker
from shopagent.rag.retriever import HybridRetriever

HERE = Path(__file__).parent
MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3-int8")


def load(name: str) -> list[dict[str, Any]]:
    spec = yaml.safe_load((HERE / name).read_text(encoding="utf-8"))
    return [q for q in spec["queries"] if "as_of" not in q]  # temporal cases need extra clauses


async def score_all(retriever: HybridRetriever, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        results = await retriever.retrieve(item["q"], top_k=4)
        rows.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "expected": item["expected"],
                "ids": [r["clause_id"] for r in results],
                "top": results[0]["score"] if results else -math.inf,
            }
        )
    return rows


def calibrate(rows: list[dict[str, Any]]) -> float:
    """Threshold maximising balanced accuracy (kept answerable + rejected out-of-domain)."""
    answerable = [r["top"] for r in rows if r["expected"]]
    out_of_domain = [r["top"] for r in rows if not r["expected"]]
    candidates = sorted({r["top"] for r in rows if math.isfinite(r["top"])})
    best_threshold, best_score = candidates[0], -1.0
    for threshold in candidates:
        kept = sum(s >= threshold for s in answerable) / len(answerable)
        rejected = sum(s < threshold for s in out_of_domain) / len(out_of_domain)
        if (kept + rejected) / 2 > best_score:
            best_threshold, best_score = threshold, (kept + rejected) / 2
    return best_threshold


def report(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    answerable = [r for r in rows if r["expected"]]
    out_of_domain = [r for r in rows if not r["expected"]]
    kept = [r for r in answerable if r["top"] >= threshold]

    def hit(r: dict[str, Any], k: int) -> float:
        return len({c for c in r["ids"][:k] if c in r["expected"]}) / len(r["expected"]) if r["top"] >= threshold else 0.0

    def top1_relevant(r: dict[str, Any]) -> float:
        """Recall@1 as in bench.py: the first result is one of the clauses that answer the question."""
        return float(r["top"] >= threshold and bool(r["ids"]) and r["ids"][0] in r["expected"])

    def rank_of_first(r: dict[str, Any]) -> float:
        if r["top"] < threshold:
            return 0.0
        return next((1 / (i + 1) for i, c in enumerate(r["ids"]) if c in r["expected"]), 0.0)

    by_kind: dict[str, float] = {}
    for kind in sorted({r["kind"] for r in answerable}):
        group = [r for r in answerable if r["kind"] == kind]
        by_kind[kind] = round(sum(hit(r, 4) for r in group) / len(group), 3)
    return {
        "threshold": round(threshold, 3),
        "answerable": len(answerable),
        "out_of_domain": len(out_of_domain),
        "recall@1": round(sum(top1_relevant(r) for r in answerable) / len(answerable), 3),
        # Stricter: share of ALL required clauses already in first place (multi-intent questions cap below 1).
        "recall@1_all_required": round(sum(hit(r, 1) for r in answerable) / len(answerable), 3),
        "recall@4": round(sum(hit(r, 4) for r in answerable) / len(answerable), 3),
        "mrr": round(sum(rank_of_first(r) for r in answerable) / len(answerable), 3),
        "unsupported_rejection": round(sum(r["top"] < threshold for r in out_of_domain) / len(out_of_domain), 3),
        "false_rejection": round((len(answerable) - len(kept)) / len(answerable), 3),
        "recall@4_by_kind": by_kind,
        "missed_out_of_domain": [r["id"] for r in out_of_domain if r["top"] >= threshold],
        "falsely_rejected": [r["id"] for r in answerable if r["top"] < threshold],
    }


async def run(restore: bool) -> dict[str, Any]:
    if not restore:
        retriever_module._Snapshot.restore_diacritics = lambda self, query: query  # type: ignore[method-assign]
    retriever = HybridRetriever(in_memory=True, reranker=CrossEncoderReranker(MODEL), min_rerank_score=None)
    calibration = await score_all(retriever, load("policy_queries_independent.yaml"))
    holdout = await score_all(retriever, load("policy_queries_holdout.yaml"))
    threshold = calibrate(calibration)
    return {
        "diacritic_restoration": restore,
        "calibration": report(calibration, threshold),
        "holdout": report(holdout, threshold),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--no-restoration-ablation", action="store_true", help="also report without diacritic restoration")
    args = parser.parse_args()
    results = [asyncio.run(run(True))]
    if args.no_restoration_ablation:
        retriever_module.clear_retrieval_caches()
        results.append(asyncio.run(run(False)))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
