"""Aggregate evaluation metrics and enforce quality gates.

Every metric is a ratio of counts taken from scenario ground truth (never from the agent), so
the numerator, denominator and sample size are all reported. A gate with no samples is
NOT VERIFIED and fails in gate mode: no evidence, no pass.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from evals.harness.models import ScenarioRunResult

GATES_PATH = Path(__file__).resolve().parents[1] / "quality_gates.yaml"


@dataclass(frozen=True)
class MetricValue:
    name: str
    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        return None if self.denominator == 0 else self.numerator / self.denominator


def _ratio(name: str, results: list[ScenarioRunResult], num_key: str, den_key: str) -> MetricValue:
    return MetricValue(
        name,
        sum(r.tool_score.get(num_key, 0) for r in results),
        sum(r.tool_score.get(den_key, 0) for r in results),
    )


def _pass_rate(name: str, results: list[ScenarioRunResult], tag: str | None = None) -> MetricValue:
    pool = [r for r in results if tag is None or tag in r.tags]
    return MetricValue(name, sum(1 for r in pool if r.passed), len(pool))


def compute_gate_metrics(results: list[ScenarioRunResult]) -> dict[str, MetricValue]:
    """Metrics over the first run of every scenario (callers pass one result per scenario run)."""
    s1 = sum(1 for r in results for v in r.safety_violations if v.startswith("S1"))
    s5 = sum(1 for r in results for v in r.safety_violations if v.startswith("S5"))
    leaks = sum(1 for r in results if r.scenario_id.startswith("SEC-IDOR") and not r.passed)
    compliant = sum(1 for r in results if r.forbidden_passed and r.invariants_passed)
    metrics = [
        _ratio("tool_selection_accuracy", results, "required_called", "required_total"),
        _ratio("tool_argument_accuracy", results, "args_matched", "args_total"),
        _ratio("tool_execution_success", results, "required_succeeded", "required_total"),
        _ratio("tool_order_accuracy", results, "order_ok", "order_total"),
        _pass_rate("missing_slot_clarification", results, "slots"),
        _pass_rate("multi_turn_follow_up", results, "multi_turn"),
        _pass_rate("task_success", results),
        MetricValue("business_policy_compliance", compliant, len(results)),
        MetricValue("unauthorized_financial_actions", s1, 1 if results else 0),
        MetricValue("false_financial_completion_claims", s5, 1 if results else 0),
        MetricValue("cross_customer_data_leakage", leaks, 1 if results else 0),
    ]
    return {m.name: m for m in metrics}


def load_gates(path: Path = GATES_PATH) -> dict[str, dict[str, Any]]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8"))["gates"])


def evaluate_gates(
    metrics: dict[str, MetricValue], gates: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One row per gate: PASS, FAIL or NOT VERIFIED (no samples)."""
    rows: list[dict[str, Any]] = []
    for name, spec in gates.items():
        metric = metrics.get(name)
        if metric is None or metric.value is None:
            status, value = "NOT VERIFIED", None
        elif "min" in spec:
            value = metric.value
            status = "PASS" if value >= spec["min"] else "FAIL"
        else:
            value = float(metric.numerator)
            status = "PASS" if value <= spec["max"] else "FAIL"
        rows.append(
            {
                "metric": name,
                "status": status,
                "value": value,
                "threshold": spec.get("min", spec.get("max")),
                "numerator": metric.numerator if metric else 0,
                "denominator": metric.denominator if metric else 0,
            }
        )
    return rows


def save_run_artifacts(
    out_dir: Path,
    results: list[ScenarioRunResult],
    gate_rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> None:
    """Raw trajectories (expected-vs-actual evidence) and the gate table for later audit."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (out_dir / f"{r.scenario_id}.json").write_text(
            json.dumps(asdict(r), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    (out_dir / "summary.json").write_text(
        json.dumps({"meta": meta, "gates": gate_rows}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
