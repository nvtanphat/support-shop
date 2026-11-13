"""Run scenarios end to end against an agent and grade the outcome.

    uv run python -m evals.harness.runner --agent oracle --gate
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from shopagent.core.clock import Clock, set_global_clock
from shopagent.core.config import get_rules_config, get_settings
from shopagent.core.principal import Principal
from shopagent.domain.policies.rules import PolicyRules
from shopagent.domain.services.actions import ActionService
from shopagent.infra.db.tables import Base, EvidenceFileModel, ReturnRequestModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from evals.harness.fixtures import setup_scenario_fixtures
from evals.harness.gates import compute_gate_metrics, evaluate_gates, load_gates, save_run_artifacts
from evals.harness.graders import (
    check_safety_invariants,
    grade_db_state,
    grade_forbidden_patterns,
    grade_required_facts,
)
from evals.harness.langgraph_agent import LangGraphAgent
from evals.harness.metrics import EvalSummary, compute_eval_metrics
from evals.harness.models import Scenario, ScenarioRunResult
from evals.harness.null_agent import NullAgent
from evals.harness.oracle_agent import OracleAgent
from evals.harness.scenario_loader import load_scenario_from_yaml
from evals.harness.scripted_user import ScriptedUser
from evals.harness.staff_actor import StaffActor
from evals.harness.tool_graders import grade_tool_execution, score_tool_use

SCENARIO_DIR = Path("evals/scenarios")
EVAL_DB_PATH = Path("evals/results/eval_fixtures.sqlite")

__all__ = ["eval_database_url", "load_scenario_from_yaml", "run_eval_cli", "run_scenario"]


def eval_database_url() -> str:
    """Database the harness is allowed to wipe. It is never the application database."""
    url = os.environ.get("EVAL_DATABASE_URL") or f"sqlite+aiosqlite:///{EVAL_DB_PATH.as_posix()}"
    if url == get_settings().DATABASE_URL:
        raise RuntimeError("EVAL_DATABASE_URL must differ from DATABASE_URL: the harness drops every table")
    if "postgres" in url and not url.rsplit("/", 1)[-1].endswith(("_eval", "_test")):
        raise RuntimeError("Refusing to wipe a PostgreSQL database whose name does not end in _eval or _test")
    return url


_eval_engine: AsyncEngine | None = None


def get_eval_engine() -> AsyncEngine:
    global _eval_engine
    if _eval_engine is None:
        _eval_engine = create_async_engine(eval_database_url())
    return _eval_engine


@dataclass
class Trajectory:
    """Everything observed while a scenario ran."""

    dialogue: list[dict[str, Any]] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


async def _reset_eval_database() -> async_sessionmaker[AsyncSession]:
    EVAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = get_eval_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _build_agent(agent_type: str, session: AsyncSession, principal: Principal, scenario: Scenario, clock: datetime, langgraph_app: Any) -> Any:
    if agent_type == "oracle":
        return OracleAgent(session=session, principal=principal, scenario=scenario)
    if agent_type == "null":
        return NullAgent(session=session)
    if agent_type in ("langgraph", "main"):
        return LangGraphAgent(session=session, principal=principal, clock=clock)
    return langgraph_app


async def _resolve_staff(staff_actor: StaffActor, session: AsyncSession, trajectory: Trajectory) -> None:
    for note in await staff_actor.step(session):
        trajectory.events.append({"type": "staff.action", "note": note})


async def _supply_evidence(session: AsyncSession, return_code: str, trajectory: Trajectory) -> None:
    """The simulated customer uploads the photos/video the policy asks for, as a real one does in the UI."""
    ret = (await session.execute(select(ReturnRequestModel).where(ReturnRequestModel.code == return_code))).scalar_one()
    rules = PolicyRules.model_validate(get_rules_config()).return_policy.evidence
    kinds = ["photo"] * rules.min_photos + (["video"] if ret.reason_code in rules.video_required_for else [])
    for index, kind in enumerate(kinds):
        session.add(
            EvidenceFileModel(return_id=ret.id, kind=kind, path=f"eval://{return_code}/{index}", sha256=f"{index:064d}", size=1, uploaded_by="customer")
        )
    await session.flush()
    trajectory.events.append({"type": "evidence.uploaded", "return_code": return_code, "files": len(kinds)})


async def _apply_user_decision(
    decision: str,
    pending: dict[str, Any],
    service: ActionService,
    principal: Principal,
    staff_actor: StaffActor,
    session: AsyncSession,
    trajectory: Trajectory,
) -> None:
    action_id = uuid.UUID(pending["id"])
    if decision == "confirm":
        result = await service.confirm_action(action_id=action_id, preview_hash=pending["preview_hash"], principal=principal)
        trajectory.events.append({"type": "action.confirmed", "action_id": str(action_id)})
        if result.get("requires_evidence") and result.get("return_code"):
            await _supply_evidence(session, result["return_code"], trajectory)
        await _resolve_staff(staff_actor, session, trajectory)  # approvals created by the confirmation
    elif decision == "cancel":
        await service.cancel_action(action_id=action_id, principal=principal)
        trajectory.events.append({"type": "action.cancelled", "action_id": str(action_id)})


async def _play_conversation(
    scenario: Scenario,
    agent: Any,
    session: AsyncSession,
    principal: Principal,
) -> tuple[Trajectory, ScriptedUser]:
    conversation_id = str(uuid.uuid4())
    scripted_user = ScriptedUser(scenario.user)
    staff_actor = StaffActor(scenario.staff)
    service = ActionService(session)
    trajectory = Trajectory()
    last_reply: str | None = None
    pending: dict[str, Any] | None = None

    for _ in range(scenario.user.max_turns or 10):
        say, decision, _card = scripted_user.respond(assistant_text=last_reply, pending_action=pending)
        trajectory.dialogue.append({"role": "customer", "content": say})

        if decision and pending:
            await _apply_user_decision(decision, pending, service, principal, staff_actor, session, trajectory)
            pending = None
        await _resolve_staff(staff_actor, session, trajectory)

        reply, tool_calls, proposal = await agent.step(
            conversation_id=conversation_id,
            user_message=say,
            dialogue_history=trajectory.dialogue,
        )
        last_reply = reply
        trajectory.replies.append(reply)
        trajectory.tool_calls.extend(tool_calls)
        trajectory.dialogue.append(
            {
                "role": "assistant",
                "content": reply,
                "tool_calls": tool_calls,
                "proposal": proposal,
                "verification_error": getattr(agent, "last_verification_error", None),
            }
        )
        if proposal:
            pending = proposal
            trajectory.events.append({"type": "action.proposed", "action_id": proposal.get("id"), "action_type": proposal.get("type")})
        if len(scripted_user._matched_steps) >= len(scenario.user.script) and not pending:
            break

    await staff_actor.step(session)  # resolve anything the last turn triggered
    await session.commit()
    return trajectory, scripted_user


async def _grade(scenario: Scenario, session: AsyncSession, trajectory: Trajectory, scripted_user: ScriptedUser, agent: Any, started: float) -> ScenarioRunResult:
    expect = scenario.expect
    calls = trajectory.tool_calls
    db_ok, db_errors = await grade_db_state(session, expect.db)
    facts_ok, facts_errors = grade_required_facts(trajectory.replies, expect.required_facts)
    tool_names = [call.get("tool") or call.get("name", "") for call in calls]
    forbidden_ok, forbidden_errors = grade_forbidden_patterns(trajectory.replies, tool_names, expect.forbidden)
    invariants_ok, invariant_errors = check_safety_invariants(calls, trajectory.events, trajectory.replies)
    tools_ok, tools_errors = grade_tool_execution(
        tool_calls=calls,
        required_tools=expect.required_tools,
        required_args=expect.required_tool_args,
        ordering_constraints=expect.tool_ordering,
    )
    return ScenarioRunResult(
        scenario_id=scenario.id,
        passed=db_ok and facts_ok and forbidden_ok and invariants_ok and tools_ok,
        db_passed=db_ok,
        facts_passed=facts_ok,
        forbidden_passed=forbidden_ok,
        invariants_passed=invariants_ok,
        tool_calls_count=len(calls),
        turns_count=len(trajectory.dialogue) // 2,
        fallback_turns=scripted_user.fallback_turns,
        errors=db_errors + facts_errors + forbidden_errors + tools_errors + invariant_errors,
        safety_violations=invariant_errors,
        dialogue=trajectory.dialogue,
        tags=list(scenario.tags),
        tool_score=score_tool_use(
            calls,
            required_tools=expect.required_tools,
            required_args=expect.required_tool_args,
            ordering_constraints=expect.tool_ordering,
        ),
        duration_s=round(time.perf_counter() - started, 2),
        usage=dict(getattr(agent, "usage", {})),
        tool_calls=calls,
    )


async def run_scenario(
    scenario: Scenario,
    agent_type: str = "oracle",
    langgraph_app: Any = None,
) -> ScenarioRunResult:
    """Execute a single scenario end to end and grade the result."""
    started = time.perf_counter()
    session_factory = await _reset_eval_database()
    clock_dt = datetime.fromisoformat(scenario.clock)
    set_global_clock(Clock(fixed_now=clock_dt))

    async with session_factory() as session:
        principal, _ = await setup_scenario_fixtures(session, scenario, clock_dt)
        agent = _build_agent(agent_type, session, principal, scenario, clock_dt, langgraph_app)
        trajectory, scripted_user = await _play_conversation(scenario, agent, session, principal)
        return await _grade(scenario, session, trajectory, scripted_user, agent, started)


def _select_scenarios(group: str, tag: str, scenario_ids: list[str] | None) -> list[Scenario]:
    selected: list[Scenario] = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        scenario = load_scenario_from_yaml(path)
        if scenario_ids and scenario.id not in scenario_ids:
            continue
        if group != "all" and not scenario.group.startswith(group):
            continue
        if tag and tag != "all" and tag not in scenario.tags:
            continue
        selected.append(scenario)
    return selected


def _print_overview(summary: EvalSummary, gate_rows: list[dict[str, Any]], target: Path) -> None:
    print("KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN:")
    print(f"Tổng số kịch bản: {summary.total_scenarios}")
    for k_value, rate in summary.pass_k.items():
        print(f"pass^{k_value}: {rate:.1f}%")
    print(f"Tỉ lệ đạt theo nhóm: {summary.group_pass_rates}")
    print(f"Số vi phạm an toàn: {summary.safety_violations_count}")
    print(f"Tỉ lệ câu thoái thác: {summary.average_fallback_rate:.1f}%")
    for row in gate_rows:
        value = "n/a" if row["value"] is None else f"{row['value']:.3f}"
        print(f"GATE {row['status']:12} {row['metric']:36} {value} (ngưỡng {row['threshold']}, mẫu {row['numerator']}/{row['denominator']})")
    print(f"Artifact: {target}")


async def run_eval_cli(
    agent: str = "oracle",
    group: str = "all",
    mode: str = "offline",
    tag: str = "smoke",
    k: int = 1,
    gate: bool = False,
    out_dir: Path | None = None,
    scenario_ids: list[str] | None = None,
) -> tuple[EvalSummary, list[dict[str, Any]]]:
    """Run scenarios, save raw trajectories and gate table; return the summary and gate rows."""
    scenarios = _select_scenarios(group, tag, scenario_ids)
    print(f"Bắt đầu đánh giá: {len(scenarios)} kịch bản | agent={agent} | group={group} | mode={mode} | k={k}", flush=True)

    runs: dict[str, list[ScenarioRunResult]] = {}
    for scenario in scenarios:
        runs[scenario.id] = []
        for attempt in range(k):
            result = await run_scenario(scenario=scenario, agent_type=agent)
            runs[scenario.id].append(result)
            error_note = f" | Lỗi: {result.errors}" if not result.passed else ""
            print(
                f"[{'PASS' if result.passed else 'FAIL'}] {scenario.id} (lần {attempt + 1}/{k}) | turns={result.turns_count} | "
                f"tools={result.tool_calls_count} | {result.duration_s}s{error_note}",
                flush=True,
            )

    summary = compute_eval_metrics(runs, k_values=list(range(1, k + 1)))
    every_run = [r for group_runs in runs.values() for r in group_runs]
    gate_rows = evaluate_gates(compute_gate_metrics(every_run), load_gates())

    run_id = f"{agent}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    target = out_dir or Path("evals/results") / run_id
    save_run_artifacts(
        target,
        every_run,
        gate_rows,
        {"agent": agent, "k": k, "scenarios": len(scenarios), "group": group, "tag": tag, "run_id": run_id},
    )
    _print_overview(summary, gate_rows, target)
    if gate and any(row["status"] != "PASS" for row in gate_rows):
        print("QUALITY GATE: FAILED hoặc NOT VERIFIED", flush=True)
    return summary, gate_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Shop Support Agent Evaluation Suite")
    parser.add_argument("--agent", choices=["oracle", "null", "langgraph"], default="oracle", help="Agent implementation")
    parser.add_argument("-k", "--k", type=int, default=1, help="Independent runs per scenario")
    parser.add_argument("--group", default="all", help="Scenario group filter")
    parser.add_argument("--tag", default="all", help="Scenario tag filter")
    parser.add_argument("--gate", action="store_true", help="Exit 1 unless every quality gate PASSes")
    parser.add_argument("--scenario", action="append", dest="scenarios", help="Run only this scenario id (repeatable)")
    parser.add_argument("--out", type=Path, default=None, help="Directory for raw trajectories and the gate table")
    args = parser.parse_args()

    _, rows = asyncio.run(
        run_eval_cli(agent=args.agent, k=args.k, group=args.group, tag=args.tag, gate=args.gate, out_dir=args.out, scenario_ids=args.scenarios)
    )
    sys.exit(1 if args.gate and any(row["status"] != "PASS" for row in rows) else 0)


if __name__ == "__main__":
    main()
