"""Re-grade a stored run with the current text graders (forbidden claims, required facts).

Grading is deterministic on the raw trajectory, so a grader fix does not need new model calls. Only the
text assertions are recomputed; database state, tool-use and safety verdicts are kept exactly as recorded
because they need the original database. The output is a new run directory; the original is untouched.

    uv run python -m evals.regrade SOURCE_RUN_DIR TARGET_RUN_DIR
"""

from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

from evals.harness.gates import compute_gate_metrics, evaluate_gates, load_gates, save_run_artifacts
from evals.harness.graders import grade_forbidden_patterns, grade_required_facts
from evals.harness.models import ScenarioRunResult
from evals.harness.runner import load_scenario_from_yaml

TEXT_CATEGORIES = ("Forbidden", "Required")  # error prefixes owned by the two re-graded assertions


def regrade(source: Path, target: Path) -> list[str]:
    changed: list[str] = []
    results: list[ScenarioRunResult] = []
    known = {f.name for f in fields(ScenarioRunResult)}
    for path in sorted(source.glob("*.json")):
        if path.name == "summary.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = ScenarioRunResult(**{k: v for k, v in raw.items() if k in known})
        scenario = load_scenario_from_yaml(Path("evals/scenarios") / f"{result.scenario_id}.yaml")
        replies = [t["content"] for t in result.dialogue if t["role"] == "assistant"]
        tool_names = [c.get("tool", "") for c in result.tool_calls]
        facts_ok, fact_errors = grade_required_facts(replies, scenario.expect.required_facts)
        forb_ok, forb_errors = grade_forbidden_patterns(replies, tool_names, scenario.expect.forbidden)
        kept = [e for e in result.errors if not e.startswith(TEXT_CATEGORIES)]
        errors = kept + fact_errors + forb_errors
        passed = not errors
        if (passed, errors) != (result.passed, result.errors):
            changed.append(f"{result.scenario_id}: {'PASS' if result.passed else 'FAIL'} -> {'PASS' if passed else 'FAIL'}")
        result.errors, result.passed = errors, passed
        result.facts_passed, result.forbidden_passed = facts_ok, forb_ok
        results.append(result)
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    rows = evaluate_gates(compute_gate_metrics(results), load_gates())
    meta = {**summary["meta"], "regraded_from": str(source), "regraded_changes": changed}
    save_run_artifacts(target, results, rows, meta)
    return changed


if __name__ == "__main__":
    for line in regrade(Path(sys.argv[1]), Path(sys.argv[2])) or ["no verdict changed"]:
        print(line)
