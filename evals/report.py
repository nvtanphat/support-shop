"""Render docs/eval-report.md from raw run artifacts, so no number in it is typed by hand.

    uv run python -m evals.report --oracle DIR --null DIR --gemini DIR \
        --retrieval evals/results/retrieval_benchmark.json --rag-strategy "<row name>" \
        --pytest-passed 146 --pytest-failed 0 --pytest-skipped 0 --postgres-tests 4 --ci "NOT VERIFIED"

Every acceptance row is PASS, FAIL, BLOCKED or NOT VERIFIED. Real-model rows come only from the
Gemini run directory; Oracle and Null results are reported in their own tables and never substituted.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml
from shopagent.agent.grounding import claimed_numbers, normalize_number

from evals.harness.gates import load_gates

CITATION_RE = re.compile(r"\[(POL-[A-Z0-9-]+)\]")
NUMBER_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")
GATE_ROWS = [
    ("tool_selection_accuracy", "Tool Selection Accuracy"),
    ("tool_argument_accuracy", "Tool Argument Accuracy"),
    ("tool_execution_success", "Successful Required Tool Execution"),
    ("tool_order_accuracy", "Tool execution order"),
    ("missing_slot_clarification", "Missing-Slot Clarification Accuracy"),
    ("multi_turn_follow_up", "Multi-Turn Follow-up Resolution"),
    ("task_success", "Real LLM End-to-End Task Success"),
    ("business_policy_compliance", "Business Policy Compliance"),
    ("unauthorized_financial_actions", "Unauthorized Financial Actions"),
    ("false_financial_completion_claims", "False Financial Completion Claims"),
    ("cross_customer_data_leakage", "Cross-Customer Data Leakage"),
]


def load_run(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    results = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json")) if p.name != "summary.json"
    ]
    return summary, results


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def gate_table(summary: dict[str, Any]) -> list[str]:
    lines = ["| Metric | Value | Threshold | Sample | Status |", "|---|---|---|---|---|"]
    for row in summary["gates"]:
        lines.append(
            f"| {row['metric']} | {fmt(row['value'])} | {row['threshold']} | {row['numerator']}/{row['denominator']} | {row['status']} |"
        )
    return lines


def successful_results(results: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """Clause ids and numbers found in successful tool results of a conversation."""
    clauses: set[str] = set()
    numbers: set[str] = set()
    for call in (c for r in results for c in r.get("tool_calls", [])):
        result = call.get("result")
        if not isinstance(result, dict) or result.get("error_code") or result.get("status") in ("db_error", "index_unavailable", "no_evidence"):
            continue
        text = json.dumps(result, ensure_ascii=False, default=str)
        clauses.update(re.findall(r"POL-[A-Z0-9-]+", text))
        numbers.update(normalize_number(n) for n in NUMBER_RE.findall(text))
    return clauses, numbers


def grounding_metrics(results: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """Recompute citation provenance and numeric support from raw trajectories, per assistant reply."""
    cited_ok = cited_total = claims_ok = claims_total = 0
    for r in results:
        clauses, numbers = successful_results([r])
        customer_numbers = {normalize_number(n) for d in r["dialogue"] if d["role"] == "customer" for n in NUMBER_RE.findall(d["content"])}
        for turn in r["dialogue"]:
            if turn["role"] != "assistant":
                continue
            for cited in CITATION_RE.findall(turn["content"]):
                cited_total += 1
                cited_ok += cited in clauses
            for value in claimed_numbers(turn["content"]):
                claims_total += 1
                claims_ok += value in numbers or value in customer_numbers
    return {"citation_provenance": (cited_ok, cited_total), "supported_numeric_claims": (claims_ok, claims_total)}


def _numbers_in(text: str) -> set[str]:
    """Every number written in a text, thousands separators removed (30.000 -> 30000)."""
    return {normalize_number(n) for n in NUMBER_RE.findall(text)}


def _ints_in(value: Any) -> set[str]:
    return _numbers_in(json.dumps(value, ensure_ascii=False, default=str))


def _order_totals(fixtures: dict[str, Any]) -> set[str]:
    """Amounts a person can derive from the fixture: line totals, order totals, totals net of discount/shipping."""
    derived: set[str] = set()
    for order in (fixtures or {}).get("orders", []):
        subtotal = sum(int(it["unit_price"]) * int(it["qty"]) for it in order.get("items", []))
        derived |= {str(subtotal), str(subtotal - int(order.get("discount_total", 0)) + int(order.get("shipping_fee", 0)))}
        derived |= {str(int(it["unit_price"]) * int(it["qty"])) for it in order.get("items", [])}
    return derived


def independent_numeric_support(results: list[dict[str, Any]], scenario_dir: Path, truth_files: list[Path]) -> tuple[int, int]:
    """Check every numeric claim against ground truth written independently of the agent.

    Truth = numbers in the scenario (fixtures and expected facts, authored by hand) + the hand-written
    business specification and decision table + amounts derivable from the fixture. Neither tool results
    nor the policy configuration the agent itself reads are consulted (evals must not depend on them).
    """
    spec_numbers = set().union(*(_numbers_in(f.read_text(encoding="utf-8")) for f in truth_files))
    supported = total = 0
    for r in results:
        scenario = yaml.safe_load((scenario_dir / f"{r['scenario_id']}.yaml").read_text(encoding="utf-8"))
        truth = _ints_in(scenario) | spec_numbers | _order_totals(scenario.get("fixtures", {}))
        for turn in r["dialogue"]:
            if turn["role"] != "assistant":
                continue
            for value in claimed_numbers(turn["content"]):
                total += 1
                supported += value in truth
    return supported, total


def status_for(value: float | None, threshold: float, higher_is_better: bool = True) -> str:
    if value is None:
        return "NOT VERIFIED"
    return "PASS" if (value >= threshold if higher_is_better else value <= threshold) else "FAIL"


def build(args: argparse.Namespace) -> str:
    gates = load_gates()
    out = ["# Báo cáo kiểm chứng AI Agent", "", "Sinh tự động bởi `python -m evals.report` từ artifact thô; không số nào được gõ tay.", ""]
    runs = {name: load_run(Path(p)) for name, p in (("Oracle", args.oracle), ("Null", args.null), ("Gemini", args.gemini)) if p}

    for name, (summary, results) in runs.items():
        meta = summary["meta"]
        passed = sum(1 for r in results if r["passed"])
        out += [f"## {name} (`{meta['run_id']}`, {meta['scenarios']} scenario, k={meta['k']})", ""]
        out += [f"Scenario đạt: {passed}/{len(results)}.", ""]
        if meta.get("regraded_changes"):
            out += [
                f"Chấm lại từ quỹ đạo thô của `{Path(meta['regraded_from']).name}` bằng bộ chấm đã sửa (không gọi lại mô hình); "
                "chỉ các kết luận sau thay đổi: " + "; ".join(meta["regraded_changes"]) + ".",
                "",
            ]
        out += gate_table(summary) + [""]
        if name == "Gemini":
            durations = sorted(r["duration_s"] for r in results)
            tokens_in = sum(r.get("usage", {}).get("input_tokens", 0) for r in results)
            tokens_out = sum(r.get("usage", {}).get("output_tokens", 0) for r in results)
            calls = sum(r.get("usage", {}).get("llm_calls", 0) for r in results)
            out += [
                f"Độ trễ mỗi scenario: p50 {durations[len(durations) // 2]}s, p95 {durations[int(len(durations) * 0.95) - 1]}s, "
                f"tổng {sum(durations):.0f}s. Token: {tokens_in} vào, {tokens_out} ra, {calls} lần gọi LLM.",
                "",
                "Nhóm lỗi: " + (", ".join(f"{k} x{v}" for k, v in summary.get("failure_categories", {}).items()) or "không có"),
                "",
            ]
            failed = [r for r in results if not r["passed"]]
            if failed:
                out += ["| Scenario | Nhóm lỗi | Chi tiết |", "|---|---|---|"]
                for r in failed:
                    detail = "; ".join(r["errors"])[:300].replace("|", "/")
                    out.append(f"| {r['scenario_id']} | {', '.join(r.get('failure_categories', []))} | {detail} |")
                out.append("")

    rag_rows: dict[str, dict[str, Any]] = {}
    if args.retrieval:
        rag_rows = {r["strategy"]: r for r in json.loads(Path(args.retrieval).read_text(encoding="utf-8"))}
        out += ["## Retrieval benchmark (bộ truy vấn độc lập, split test)", "", "| Strategy | R@1 | R@4 | MRR | nDCG@4 | P@4 | Từ chối OOD | Từ chối nhầm | p50 ms |", "|---|---|---|---|---|---|---|---|---|"]
        for r in rag_rows.values():
            out.append(
                f"| {r['strategy']} | {r['recall@1']} | {r['recall@4']} | {r['mrr']} | {r['ndcg@4']} | {r['precision@4']} | "
                f"{r['unsupported_rejection']} | {r['false_rejection']} | {r['latency_ms_p50']} |"
            )
        out.append("")

    holdout_rows: list[dict[str, Any]] = json.loads(Path(args.holdout).read_text(encoding="utf-8")) if args.holdout else []
    if holdout_rows:
        out += [
            "## Retrieval holdout (policy_queries_holdout, ngưỡng chốt từ bộ độc lập trước khi chấm)",
            "",
            "| Khôi phục dấu | Tập | Ngưỡng | R@1 | R@1 (đủ mọi điều khoản) | R@4 | MRR | Từ chối ngoài phạm vi | Từ chối nhầm | Mẫu (hợp lệ/ngoài phạm vi) |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in holdout_rows:
            for label, key in (("calibration", "calibration"), ("holdout", "holdout")):
                x = row[key]
                out.append(
                    f"| {'có' if row['diacritic_restoration'] else 'không'} | {label} | {x['threshold']} | {x['recall@1']} | {x['recall@1_all_required']} | {x['recall@4']} | "
                    f"{x['mrr']} | {x['unsupported_rejection']} | {x['false_rejection']} | {x['answerable']}/{x['out_of_domain']} |"
                )
        out.append("")

    # ---- acceptance matrix
    matrix: list[tuple[str, str, str, str]] = []
    pytest_ok = args.pytest_failed == 0 and args.pytest_skipped == 0 and args.pytest_passed > 0
    matrix.append(("P0/P1 regression tests", "100% pass", f"{args.pytest_passed} pass, {args.pytest_failed} fail, {args.pytest_skipped} skip", "PASS" if pytest_ok else "FAIL" if args.pytest_failed else "NOT VERIFIED"))
    if "Gemini" in runs:
        by_metric = {row["metric"]: row for row in runs["Gemini"][0]["gates"]}
        for key, label in GATE_ROWS:
            row = by_metric[key]
            spec = gates[key]
            matrix.append((label, f">= {spec['min']}" if "min" in spec else f"<= {spec['max']}", f"{fmt(row['value'])} ({row['numerator']}/{row['denominator']})", row["status"]))
        grounding = grounding_metrics(runs["Gemini"][1])
        ok, total = grounding["citation_provenance"]
        matrix.append(("Valid Citation Provenance", "100%", f"{ok}/{total} citations backed by a successful lookup", ("PASS" if ok == total else "FAIL") if total else "NOT VERIFIED"))
        ok, total = grounding["supported_numeric_claims"]
        ok_i, total_i = independent_numeric_support(
            runs["Gemini"][1],
            Path(args.scenario_dir),
            [Path(f) for f in args.truth_file],
        )
        rate = ok_i / total_i if total_i else None
        matrix.append(
            (
                "Supported Factual Claims",
                ">= 98%",
                f"{ok_i}/{total_i} numeric claims match the scenario fixtures, business spec and decision table (independent of tool results and of config); "
                f"{ok}/{total} also match successful tool results",
                status_for(rate, 0.98),
            )
        )
    else:
        for _key, label in GATE_ROWS:
            matrix.append((label, "see quality_gates.yaml", "no Gemini run supplied", "NOT VERIFIED"))
    # The independent final set (never used to tune) is gated on its own: dev-set scores cannot stand in for it.
    if args.independent:
        independent = json.loads((Path(args.independent) / "summary.json").read_text(encoding="utf-8"))
        rows = {row["metric"]: row for row in independent["gates"]}
        task = rows["task_success"]
        failed = sorted(m for m, row in rows.items() if row["status"] != "PASS")
        matrix.append(
            (
                "Independent final set, real Gemini (all gates)",
                ">= 0.9 task success, every gate",
                f"task success {fmt(task['value'])} ({task['numerator']}/{task['denominator']}, k={independent['meta'].get('k')})"
                + (f"; failing: {', '.join(failed)}" if failed else ""),
                "PASS" if not failed else "FAIL",
            )
        )
    else:
        matrix.append(("Independent final set, real Gemini (all gates)", ">= 0.9 task success, every gate", args.independent_note, "BLOCKED"))
    strategy = rag_rows.get(args.rag_strategy or "")
    held = holdout_rows[0]["holdout"] if holdout_rows else None
    if held:
        note = f" (holdout, n={held['answerable']}/{held['out_of_domain']}, ngưỡng chốt từ bộ độc lập)"
        matrix.append(("RAG Recall@1", ">= 0.90", f"{held['recall@1']}{note}", status_for(held["recall@1"], 0.90)))
        matrix.append(("RAG Recall@4", ">= 0.95", f"{held['recall@4']}{note}", status_for(held["recall@4"], 0.95)))
        matrix.append(("Unsupported-Query Rejection", ">= 0.95", f"{held['unsupported_rejection']}{note}", status_for(held["unsupported_rejection"], 0.95)))
    elif strategy:
        matrix.append(("RAG Recall@1", ">= 0.90", str(strategy["recall@1"]), status_for(strategy["recall@1"], 0.90)))
        matrix.append(("RAG Recall@4", ">= 0.95", str(strategy["recall@4"]), status_for(strategy["recall@4"], 0.95)))
        matrix.append(("Unsupported-Query Rejection", ">= 0.95", str(strategy["unsupported_rejection"]), status_for(strategy["unsupported_rejection"], 0.95)))
    else:
        for label, bar in (("RAG Recall@1", ">= 0.90"), ("RAG Recall@4", ">= 0.95"), ("Unsupported-Query Rejection", ">= 0.95")):
            matrix.append((label, bar, "no benchmark row selected", "NOT VERIFIED"))
    matrix.append(("Checkpoint and State Recovery", "100% pass", f"{args.postgres_tests} PostgreSQL tests pass" if args.postgres_tests else "not run", "PASS" if args.postgres_tests else "NOT VERIFIED"))
    matrix.append(("Required Backend/Frontend CI Checks", "100% pass", "GitHub Actions status", args.ci))

    out += ["## Ma trận nghiệm thu", "", "| Tiêu chí | Ngưỡng | Kết quả đo | Trạng thái |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in matrix]
    verdict = "PASS" if all(row[3] == "PASS" for row in matrix) else "BLOCKED / NOT VERIFIED" if not any(row[3] == "FAIL" for row in matrix) else "FAIL"
    out += ["", f"**AI AGENT ACCEPTANCE: {verdict}**", ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle")
    parser.add_argument("--null")
    parser.add_argument("--gemini")
    parser.add_argument("--retrieval")
    parser.add_argument("--independent", help="Run directory of the independent final scenario set (--set holdout)")
    parser.add_argument("--independent-note", default="not run", help="Why the independent run is missing, shown in the matrix")
    parser.add_argument("--rag-strategy")
    parser.add_argument("--holdout", help="JSON from evals.retrieval.holdout; preferred over --retrieval for the RAG rows")
    parser.add_argument("--pytest-passed", type=int, default=0)
    parser.add_argument("--pytest-failed", type=int, default=0)
    parser.add_argument("--pytest-skipped", type=int, default=0)
    parser.add_argument("--postgres-tests", type=int, default=0)
    parser.add_argument("--ci", default="NOT VERIFIED")
    parser.add_argument("--scenario-dir", default="evals/scenarios", help="Scenario YAML files (independent ground truth)")
    parser.add_argument(
        "--truth-file",
        action="append",
        default=None,
        help="Hand-written files whose numbers count as independent truth (repeatable)",
    )
    parser.add_argument("--notes", type=Path, default=Path("docs/eval-notes.md"), help="Hand-written limits of the evidence, appended as is")
    parser.add_argument("--out", type=Path, default=Path("docs/eval-report.md"))
    args = parser.parse_args()
    args.truth_file = args.truth_file or ["docs/business-spec.md", "evals/ground_truth/policy_decision_table.csv"]
    report = build(args)
    if args.notes.exists():
        report = report.rstrip() + "\n\n" + args.notes.read_text(encoding="utf-8").strip() + "\n"
    args.out.write_text(report, encoding="utf-8")
    print(f"Đã ghi {args.out}")


if __name__ == "__main__":
    main()
