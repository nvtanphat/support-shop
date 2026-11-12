"""The evaluation report is derived from artifacts and never passes on missing evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.harness.gates import load_gates
from evals.report import build, grounding_metrics


def write_run(directory: Path, gate_values: dict[str, float | None]) -> None:
    directory.mkdir()
    gates = [
        {"metric": name, "status": "NOT VERIFIED" if v is None else "PASS", "value": v, "threshold": spec.get("min", spec.get("max")), "numerator": 1, "denominator": 1}
        for name, spec in load_gates().items()
        for v in [gate_values.get(name, 1.0 if "min" in spec else 0.0)]
    ]
    (directory / "summary.json").write_text(json.dumps({"meta": {"run_id": "t", "scenarios": 1, "k": 1}, "gates": gates, "failure_categories": {}}), encoding="utf-8")
    (directory / "S-1.json").write_text(
        json.dumps(
            {
                "scenario_id": "S-1", "passed": True, "errors": [], "duration_s": 1.0, "usage": {},
                "dialogue": [
                    {"role": "customer", "content": "đổi ý trả hàng"},
                    {"role": "assistant", "content": "Theo [POL-RETURN-02] trong 7 ngày; [POL-FAKE-99] 45 ngày."},
                ],
                "tool_calls": [{"tool": "search_policy", "result": {"status": "success", "results": [{"clause_id": "POL-RETURN-02", "text": "trong 7 ngày"}]}}],
            }
        ),
        encoding="utf-8",
    )


def namespace(**overrides) -> argparse.Namespace:  # type: ignore[no-untyped-def]
    base = {"oracle": None, "null": None, "gemini": None, "retrieval": None, "rag_strategy": None, "pytest_passed": 10, "pytest_failed": 0, "pytest_skipped": 0, "postgres_tests": 4, "ci": "PASS"}
    return argparse.Namespace(**{**base, **overrides})


def test_provenance_and_numeric_support_are_recomputed_from_raw_trajectories(tmp_path: Path) -> None:
    write_run(tmp_path / "g", {})
    result = json.loads((tmp_path / "g" / "S-1.json").read_text(encoding="utf-8"))
    metrics = grounding_metrics([result])
    assert metrics["citation_provenance"] == (1, 2)  # POL-FAKE-99 was never retrieved
    assert metrics["supported_numeric_claims"] == (1, 2)  # 45 ngày has no source


def test_report_never_passes_without_gemini_or_retrieval_evidence(tmp_path: Path) -> None:
    text = build(namespace())
    assert "AI AGENT ACCEPTANCE: BLOCKED / NOT VERIFIED" in text
    assert "Real LLM End-to-End Task Success | see quality_gates.yaml | no Gemini run supplied | NOT VERIFIED" in text


def test_report_fails_when_a_measured_gate_fails_and_keeps_oracle_separate(tmp_path: Path) -> None:
    write_run(tmp_path / "oracle", {})
    write_run(tmp_path / "gemini", {"task_success": None})
    text = build(namespace(oracle=str(tmp_path / "oracle"), gemini=str(tmp_path / "gemini")))
    assert "## Oracle" in text and "## Gemini" in text
    # Real-model rows come only from the Gemini run: its missing task_success cannot be covered by Oracle.
    assert "Real LLM End-to-End Task Success | >= 0.9 | n/a (1/1) | NOT VERIFIED" in text
    assert "Valid Citation Provenance | 100% | 1/2" in text and "| FAIL |" in text
