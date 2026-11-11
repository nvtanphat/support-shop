"""Evaluation metrics calculation: pass^k, safety invariant counts, fallback rates."""

from __future__ import annotations

from dataclasses import dataclass, field
from evals.harness.models import ScenarioRunResult


@dataclass
class EvalSummary:
    total_scenarios: int
    runs_per_scenario: int
    pass_k: dict[int, float]  # {1: 95.0, 2: 90.0, 3: 85.0}
    group_pass_rates: dict[str, float]
    safety_violations_count: int
    average_fallback_rate: float
    results_by_scenario: dict[str, list[ScenarioRunResult]] = field(default_factory=dict)


def compute_eval_metrics(
    all_runs: dict[str, list[ScenarioRunResult]],
    k_values: list[int] | None = None,
) -> EvalSummary:
    """Compute pass^k and group metrics across multiple independent scenario runs.

    pass^k is the fraction of scenarios that pass in ALL of k consecutive runs.
    """
    if k_values is None:
        k_values = [1, 2, 3]

    total_scenarios = len(all_runs)
    if total_scenarios == 0:
        return EvalSummary(0, 0, {}, {}, 0, 0.0)

    runs_per_scenario = min(len(runs) for runs in all_runs.values()) if all_runs else 1

    pass_k_rates: dict[int, float] = {}
    for k in k_values:
        if k > runs_per_scenario:
            continue
        passed_all_k = 0
        for scenario_id, runs in all_runs.items():
            if all(r.passed for r in runs[:k]):
                passed_all_k += 1
        pass_k_rates[k] = (passed_all_k / total_scenarios) * 100.0

    # Group pass rates (pass^1)
    groups: dict[str, list[bool]] = {}
    total_fallbacks = 0
    total_turns = 0
    total_safety_violations = 0

    for scenario_id, runs in all_runs.items():
        first_run = runs[0]
        group = scenario_id.split("-")[0]
        groups.setdefault(group, []).append(first_run.passed)
        total_fallbacks += first_run.fallback_turns
        total_turns += max(1, first_run.turns_count)
        total_safety_violations += len(first_run.safety_violations)

    group_rates: dict[str, float] = {
        g: (sum(1 for p in passed_list if p) / len(passed_list)) * 100.0
        for g, passed_list in groups.items()
    }

    avg_fallback_rate = (total_fallbacks / total_turns) * 100.0 if total_turns > 0 else 0.0

    return EvalSummary(
        total_scenarios=total_scenarios,
        runs_per_scenario=runs_per_scenario,
        pass_k=pass_k_rates,
        group_pass_rates=group_rates,
        safety_violations_count=total_safety_violations,
        average_fallback_rate=avg_fallback_rate,
        results_by_scenario=all_runs,
    )
