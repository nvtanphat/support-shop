"""Check, and optionally refresh, the unsupported-question threshold after the policy corpus changes.

    uv run --extra rerank python -m evals.retrieval.calibrate            # report only
    uv run --extra rerank python -m evals.retrieval.calibrate --check    # exit 1 when the configured threshold has drifted
    uv run --extra rerank python -m evals.retrieval.calibrate --write    # write the recalibrated threshold to config/app.yaml

The threshold (config/app.yaml, retrieval.reranker.min_score) is the reranker score below which the best clause is
too weak to present as evidence. It depends on the clause texts, so it must be re-derived whenever clauses are added
or reworded. The threshold is chosen on the independent query set only; the holdout set is scored with it afterwards
and is never used to choose it (see evals/retrieval/holdout.py, whose functions this reuses).

Drift is measured as balanced accuracy on the independent set: how much worse the configured threshold does than the
best one for the current corpus. It also lists clauses no answerable query expects, because a clause nobody asks
about cannot be checked at all.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from typing import Any

import yaml
from shopagent.core.config import CONFIG_DIR, get_app_config
from shopagent.rag.indexer import build_corpus
from shopagent.rag.reranker import CrossEncoderReranker
from shopagent.rag.retriever import PolicyRetriever

from evals.retrieval.holdout import MODEL, calibrate, load, report, score_all

DRIFT_TOLERANCE = 0.03  # balanced accuracy the configured threshold may lose against the recalibrated one


def balanced_accuracy(rows: list[dict[str, Any]], threshold: float) -> float:
    answerable = [r["top"] for r in rows if r["expected"]]
    out_of_domain = [r["top"] for r in rows if not r["expected"]]
    kept = sum(s >= threshold for s in answerable) / len(answerable)
    rejected = sum(s < threshold for s in out_of_domain) / len(out_of_domain)
    return (kept + rejected) / 2


def uncovered_clauses(queries: list[dict[str, Any]]) -> list[str]:
    """Active clauses that no answerable independent or holdout query expects."""
    expected = {c for q in queries for c in q["expected"]}
    return sorted(c["clause_id"] for c in build_corpus() if c.get("status", "active") == "active" and c["clause_id"] not in expected)


def write_threshold(value: float) -> None:
    path = CONFIG_DIR / "app.yaml"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(r"(?m)^(\s*min_score:\s*)-?\d+(?:\.\d+)?", rf"\g<1>{value:.2f}", text, count=1)
    if count != 1:
        raise SystemExit("could not find retrieval.reranker.min_score in config/app.yaml")
    yaml.safe_load(updated)  # never leave an unparsable config behind
    path.write_text(updated, encoding="utf-8")


async def run(check: bool, write: bool) -> int:
    retriever = PolicyRetriever(in_memory=True, reranker=CrossEncoderReranker(MODEL), min_rerank_score=None)
    calibration = await score_all(retriever, load("policy_queries_independent.yaml"))
    holdout = await score_all(retriever, load("policy_queries_holdout.yaml"))
    suggested = calibrate(calibration)
    configured_raw = ((get_app_config().get("retrieval") or {}).get("reranker") or {}).get("min_score")
    configured = float(configured_raw) if configured_raw is not None else -math.inf

    at_configured, at_suggested = balanced_accuracy(calibration, configured), balanced_accuracy(calibration, suggested)
    drift = at_suggested - at_configured
    result = {
        "configured_threshold": configured_raw,
        "recalibrated_threshold": round(suggested, 2),
        "balanced_accuracy_configured": round(at_configured, 3),
        "balanced_accuracy_recalibrated": round(at_suggested, 3),
        "drift": round(drift, 3),
        "holdout_at_configured": report(holdout, configured),
        "holdout_at_recalibrated": report(holdout, suggested),
        "clauses_without_a_query": uncovered_clauses(load("policy_queries_independent.yaml") + load("policy_queries_holdout.yaml")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if write:
        write_threshold(suggested)
        print(f"min_score -> {suggested:.2f} in config/app.yaml", file=sys.stderr)
    drifted = drift > DRIFT_TOLERANCE
    if drifted:
        print(f"Ngưỡng đã lệch {drift:.3f} (dung sai {DRIFT_TOLERANCE}): chạy lại với --write rồi kiểm tra holdout.", file=sys.stderr)
    return 1 if (check and drifted) or (check and result["clauses_without_a_query"]) else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit 1 on drift or on a clause no query covers")
    parser.add_argument("--write", action="store_true", help="write the recalibrated threshold to config/app.yaml")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.check, args.write)))


if __name__ == "__main__":
    main()
