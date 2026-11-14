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


def namespace(tmp_path: Path | None = None, **overrides) -> argparse.Namespace:  # type: ignore[no-untyped-def]
    base = {"oracle": None, "null": None, "gemini": None, "retrieval": None, "holdout": None, "rag_strategy": None, "pytest_passed": 10, "pytest_failed": 0, "pytest_skipped": 0, "postgres_tests": 4, "ci": "PASS", "scenario_dir": "evals/scenarios", "truth_file": [], "independent": None, "independent_note": "not run"}
    if tmp_path is not None:  # a synthetic scenario S-1 and a truth file that states the policy numbers
        (tmp_path / "scenarios").mkdir(exist_ok=True)
        (tmp_path / "scenarios" / "S-1.yaml").write_text("id: S-1" + chr(10) + "expect: {}" + chr(10), encoding="utf-8")
        (tmp_path / "truth.md").write_text("Đổi ý trong 7 ngày.", encoding="utf-8")
        base |= {"scenario_dir": str(tmp_path / "scenarios"), "truth_file": [str(tmp_path / "truth.md")]}
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
    text = build(namespace(tmp_path, oracle=str(tmp_path / "oracle"), gemini=str(tmp_path / "gemini")))
    assert "## Oracle" in text and "## Gemini" in text
    # Real-model rows come only from the Gemini run: its missing task_success cannot be covered by Oracle.
    assert "Real LLM End-to-End Task Success | >= 0.9 | n/a (1/1) | NOT VERIFIED" in text
    assert "Valid Citation Provenance | 100% | 1/2" in text and "| FAIL |" in text


def test_independent_numeric_support_ignores_tool_results_and_uses_hand_written_truth(tmp_path: Path) -> None:
    from evals.report import independent_numeric_support

    ns = namespace(tmp_path)
    run = {
        "scenario_id": "S-1",
        "dialogue": [{"role": "assistant", "content": "Đổi ý trong 7 ngày, hoàn 99.000 đ."}],
        "tool_calls": [{"tool": "check_return_eligibility", "result": {"refund": 99000}}],  # tool says 99.000, truth does not
    }
    supported, total = independent_numeric_support([run], Path(ns.scenario_dir), [Path(f) for f in ns.truth_file])
    assert (supported, total) == (1, 2)  # 7 ngày is in the spec; 99.000 đ only in a tool result


def test_a_missing_independent_run_blocks_acceptance_even_when_every_dev_gate_passes(tmp_path: Path) -> None:
    write_run(tmp_path / "gemini", {})
    blocked = build(namespace(tmp_path, gemini=str(tmp_path / "gemini"), independent_note="quota exhausted"))
    assert "Independent final set, real Gemini (all gates) | >= 0.9 task success, every gate | quota exhausted | BLOCKED" in blocked
    assert "AI AGENT ACCEPTANCE: PASS" not in blocked


def test_an_unsampled_gate_of_the_independent_set_is_named_but_is_not_a_failure(tmp_path: Path) -> None:
    # A set with no multi-turn scenario cannot measure multi-turn follow-up; that is a gap to state, not a failed gate.
    write_run(tmp_path / "gemini", {})
    write_run(tmp_path / "independent", {"multi_turn_follow_up": None})
    text = build(namespace(tmp_path, gemini=str(tmp_path / "gemini"), independent=str(tmp_path / "independent")))
    row = next(line for line in text.splitlines() if line.startswith("| Independent final set"))
    assert row.endswith("| PASS |") and "not sampled: multi_turn_follow_up" in row
    write_run(tmp_path / "failing", {"task_success": 0.5})
    summary = json.loads((tmp_path / "failing" / "summary.json").read_text(encoding="utf-8"))
    for row in summary["gates"]:
        if row["metric"] == "task_success":
            row["status"] = "FAIL"
    (tmp_path / "failing" / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    failing = build(namespace(tmp_path, gemini=str(tmp_path / "gemini"), independent=str(tmp_path / "failing")))
    assert next(line for line in failing.splitlines() if line.startswith("| Independent final set")).endswith("| FAIL |")
