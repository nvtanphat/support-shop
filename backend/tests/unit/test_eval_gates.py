"""Quality gates, tool-use scoring and the evaluation database guard."""

from __future__ import annotations

import pytest

from evals.harness.gates import compute_gate_metrics, evaluate_gates, load_gates
from evals.harness.models import ScenarioRunResult
from evals.harness.runner import eval_database_url
from evals.harness.tool_graders import grade_tool_execution, score_tool_use


def run_result(**overrides) -> ScenarioRunResult:  # type: ignore[no-untyped-def]
    base = {
        "scenario_id": "RET-X-001", "passed": True, "db_passed": True, "facts_passed": True,
        "forbidden_passed": True, "invariants_passed": True, "tool_calls_count": 0,
        "turns_count": 1, "fallback_turns": 0,
    }
    return ScenarioRunResult(**{**base, **overrides})


def test_failed_tool_call_is_called_but_not_succeeded() -> None:
    calls = [{"tool": "get_order", "args": {"order_code": "SL-1"}, "result": {"error_code": "TOOL_TIMEOUT"}}]
    score = score_tool_use(calls, required_tools=["get_order"])
    assert (score["required_called"], score["required_succeeded"]) == (1, 0)
    passed, errors = grade_tool_execution(calls, required_tools=["get_order"])
    assert passed is False and "TOOL_NOT_SUCCEEDED" in errors[0]


def test_record_without_result_never_counts_as_success() -> None:
    assert score_tool_use([{"tool": "get_order", "args": {}}], required_tools=["get_order"])["required_succeeded"] == 0


def test_definitive_refusal_counts_as_executed() -> None:
    calls = [{"tool": "get_order", "args": {}, "result": {"error_code": "ORDER_NOT_FOUND"}}]
    assert score_tool_use(calls, required_tools=["get_order"])["required_succeeded"] == 1


def test_ordering_requires_both_tools_in_order() -> None:
    ok = [{"tool": "a", "result": {}}, {"tool": "b", "result": {}}]
    wrong = [{"tool": "b", "result": {}}, {"tool": "a", "result": {}}]
    missing = [{"tool": "b", "result": {}}]
    constraint = [("a", "b")]
    assert score_tool_use(ok, ordering_constraints=constraint)["order_ok"] == 1
    assert score_tool_use(wrong, ordering_constraints=constraint)["order_ok"] == 0
    assert score_tool_use(missing, ordering_constraints=constraint)["order_ok"] == 0


def test_gate_without_samples_is_not_verified_and_never_passes() -> None:
    rows = evaluate_gates(compute_gate_metrics([run_result()]), load_gates())
    status = {r["metric"]: r["status"] for r in rows}
    assert status["multi_turn_follow_up"] == "NOT VERIFIED"
    assert status["tool_selection_accuracy"] == "NOT VERIFIED"


def test_gate_fails_below_threshold_and_on_any_safety_violation() -> None:
    results = [
        run_result(scenario_id="MT-1", tags=["multi_turn"], passed=False),
        run_result(scenario_id="MT-2", tags=["multi_turn"], passed=True),
        run_result(scenario_id="RET-2", safety_violations=["S5 VIOLATION: claimed refund"], invariants_passed=False),
    ]
    status = {r["metric"]: r["status"] for r in evaluate_gates(compute_gate_metrics(results), load_gates())}
    assert status["multi_turn_follow_up"] == "FAIL"  # 1/2 < 0.95
    assert status["false_financial_completion_claims"] == "FAIL"
    assert status["unauthorized_financial_actions"] == "PASS"


def test_eval_database_is_never_the_application_database(monkeypatch: pytest.MonkeyPatch) -> None:
    from shopagent.core.config import get_settings

    monkeypatch.setenv("EVAL_DATABASE_URL", get_settings().DATABASE_URL)
    with pytest.raises(RuntimeError, match="must differ"):
        eval_database_url()
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql+asyncpg://u:p@h/shopagent")
    with pytest.raises(RuntimeError, match="_eval or _test"):
        eval_database_url()
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql+asyncpg://u:p@h/shopagent_eval")
    assert eval_database_url().endswith("shopagent_eval")


def test_failures_are_bucketed_by_cause() -> None:
    from evals.harness.gates import categorize_failure, failure_category_counts

    assert categorize_failure("MISSING_TOOL: Required tool 'x' was not invoked") == "tool_selection"
    assert categorize_failure("ARGUMENT_MISMATCH: Tool 'x'") == "tool_arguments"
    assert categorize_failure("Assistant never asked the customer for missing slot 'item'") == "missing_slot_clarification"
    assert categorize_failure("S5 VIOLATION: claimed refund") == "safety_invariant"
    assert categorize_failure("Required clause citation '[POL-1]' not found") == "missing_required_fact"
    assert categorize_failure("something unexpected") == "other"
    failed = [run_result(passed=False, errors=["MISSING_TOOL: a", "MISSING_TOOL: b", "DB Order X not found"])]
    assert failure_category_counts(failed) == {"tool_selection": 2, "database_state": 1}
