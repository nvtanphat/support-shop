"""Evaluation Harness Scenario Runner."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from shopagent.core.clock import Clock, set_global_clock
from shopagent.core.config import get_settings
from shopagent.core.principal import Principal
from shopagent.domain.models.enums import PaymentStatus
from shopagent.domain.services.actions import ActionService
from shopagent.infra.db.tables import (
    Base,
    CustomerModel,
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductVariantModel,
    StaffUserModel,
)
from shopagent.rag.indexer import index_policies
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from evals.harness.gates import compute_gate_metrics, evaluate_gates, load_gates, save_run_artifacts
from evals.harness.graders import (
    check_safety_invariants,
    grade_db_state,
    grade_forbidden_patterns,
    grade_required_facts,
    grade_tool_execution,
    score_tool_use,
)
from evals.harness.langgraph_agent import LangGraphAgent
from evals.harness.metrics import EvalSummary, compute_eval_metrics
from evals.harness.models import (
    SUPPORTED_DB_TABLES,
    SUPPORTED_EXPECT_KEYS,
    SUPPORTED_FORBIDDEN_KINDS,
    SUPPORTED_REQUIRED_FACT_KINDS,
    ForbiddenPattern,
    RequiredFact,
    Scenario,
    ScenarioExpectation,
    ScenarioRunResult,
    ScriptStep,
    StaffAction,
    UserScript,
)
from evals.harness.null_agent import NullAgent
from evals.harness.oracle_agent import OracleAgent
from evals.harness.scripted_user import ScriptedUser
from evals.harness.staff_actor import StaffActor


def load_scenario_from_yaml(path: Path) -> Scenario:
    """Parse scenario definition from YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    user_data = data.get("user", {})
    script_steps = [
        ScriptStep(
            say=st.get("say", ""),
            when_asked=st.get("when_asked"),
            on_proposal=st.get("on_proposal"),
            do=st.get("do"),
        )
        for st in user_data.get("script", [])
    ]
    user_script = UserScript(
        goal=user_data.get("goal", ""),
        script=script_steps,
        fallback_say=user_data.get("fallback_say", "Bạn cần mình cung cấp thông tin gì?"),
        max_turns=user_data.get("max_turns", 10),
    )

    staff_actions = [
        StaffAction(
            when_event=sa.get("when_event", "approval.created"),
            gate=sa.get("gate", "*"),
            decision=sa.get("decision", "approve"),
            role=sa.get("role", "agent"),
            note=sa.get("note", ""),
        )
        for sa in data.get("staff", [])
    ]

    expect_data = data.get("expect", {})
    req_facts = [
        RequiredFact(
            kind=rf.get("kind", ""),
            value=rf.get("value"),
            id=rf.get("id"),
            note=rf.get("note", ""),
        )
        for rf in expect_data.get("required_facts", [])
    ]
    forbidden_patterns = [
        ForbiddenPattern(
            kind=fp.get("kind", "claim"),
            pattern=fp.get("pattern", ""),
        )
        for fp in expect_data.get("forbidden", [])
    ]

    ordering_raw = expect_data.get("tool_ordering", [])
    tool_ordering = [
        (item[0], item[1]) if isinstance(item, (list, tuple)) and len(item) == 2 else (item.get("first"), item.get("second"))
        for item in ordering_raw
    ]

    unknown_keys = set(expect_data) - SUPPORTED_EXPECT_KEYS
    unknown_tables = set(expect_data.get("db", {})) - SUPPORTED_DB_TABLES
    unknown_facts = {rf.kind for rf in req_facts} - SUPPORTED_REQUIRED_FACT_KINDS
    unknown_forbidden = {fp.kind for fp in forbidden_patterns} - SUPPORTED_FORBIDDEN_KINDS
    problems = [
        f"{label}: {sorted(bad)}"
        for label, bad in (
            ("unknown expect keys", unknown_keys),
            ("unknown db tables", unknown_tables),
            ("unknown required_fact kinds", unknown_facts),
            ("unknown forbidden kinds", unknown_forbidden),
        )
        if bad
    ]
    if problems:
        raise ValueError(f"Scenario {data.get('id', path.name)} has unsupported assertions: {'; '.join(problems)}")

    expect = ScenarioExpectation(
        db=expect_data.get("db", {}),
        required_facts=req_facts,
        forbidden=forbidden_patterns,
        max_tool_calls=expect_data.get("max_tool_calls", 10),
        required_tools=expect_data.get("required_tools", []),
        required_tool_args=expect_data.get("required_tool_args", {}),
        tool_ordering=tool_ordering,
    )

    return Scenario(
        id=data["id"],
        group=data.get("group", ""),
        tags=data.get("tags", []),
        clock=data.get("clock", "2026-11-11T10:00:00+07:00"),
        principal=data.get("principal", {}),
        fixtures=data.get("fixtures", {}),
        user=user_script,
        staff=staff_actions,
        expect=expect,
    )


async def setup_scenario_fixtures(
    session: AsyncSession,
    scenario: Scenario,
    clock_dt: datetime,
) -> tuple[Principal, list[OrderModel]]:
    """Insert scenario-specific fixture records into database."""
    # 0. Index policies into DB
    await index_policies(session)

    # 1. Staff users
    agent_staff = StaffUserModel(
        id=uuid.UUID(int=1),
        email="agent@shop.vn",
        password_hash="pwd",
        role="agent",
        full_name="Nhân Viên",
    )
    sup_staff = StaffUserModel(
        id=uuid.UUID(int=2),
        email="supervisor@shop.vn",
        password_hash="pwd",
        role="supervisor",
        full_name="Trưởng Ca",
    )
    session.add(agent_staff)
    session.add(sup_staff)

    # 2. Customer
    cust_id = uuid.uuid4()
    p_data = scenario.principal
    is_guest = p_data.get("type") == "guest"
    cust_email = p_data.get("email", "eval.customer@example.com")
    customer = CustomerModel(
        id=cust_id,
        email=cust_email,
        phone=p_data.get("phone", "0901234567"),
        full_name=p_data.get("full_name", "Khách Đánh Giá"),
        tier=p_data.get("tier", "standard"),
    )
    session.add(customer)
    await session.flush()

    if is_guest:
        principal = Principal.guest(guest_token="guest_token_eval")
        owner_id = uuid.uuid4()
        other_customer = CustomerModel(
            id=owner_id,
            email="other.owner@example.com",
            phone="0988776655",
            full_name="Chủ Đơn Hàng Khác",
            tier="standard",
        )
        session.add(other_customer)
        await session.flush()
    else:
        principal = Principal.authenticated_customer(customer_id=cust_id)
        owner_id = cust_id

    # 3. Orders & Items
    created_orders: list[OrderModel] = []
    fixtures_orders = scenario.fixtures.get("orders", [])
    for _o_idx, o_fix in enumerate(fixtures_orders):
        order_code = o_fix["code"]
        order_id = uuid.uuid4()

        # Parse relative delivered_at / placed_at
        del_at_str = o_fix.get("delivered_at")
        delivered_at = None
        if del_at_str:
            if del_at_str.endswith("d"):
                days = float(del_at_str[:-1])
                delivered_at = clock_dt + timedelta(days=days)
            else:
                delivered_at = datetime.fromisoformat(del_at_str)

        placed_at = (delivered_at - timedelta(days=2)) if delivered_at else (clock_dt - timedelta(days=1))

        # Items
        items_fixtures = o_fix.get("items", [])
        subtotal = 0
        order_items: list[OrderItemModel] = []
        for it_fix in items_fixtures:
            price = it_fix["unit_price"]
            q = it_fix["qty"]
            subtotal += price * q
            p_model = ProductModel(
                id=uuid.uuid4(),
                name=it_fix.get("key", "Sản phẩm"),
                category="fashion",
                return_flags=it_fix.get("flags", []),
            )
            v_model = ProductVariantModel(
                id=uuid.uuid4(),
                product_id=p_model.id,
                sku=it_fix["sku"],
                price=price,
                stock=50,
            )
            session.add(p_model)
            session.add(v_model)

            oi = OrderItemModel(
                id=uuid.uuid4(),
                order_id=order_id,
                variant_id=v_model.id,
                qty=q,
                unit_price=price,
                allocated_discount=0,
                returned_qty=0,
                exchanged=False,
            )
            order_items.append(oi)

        discount_total = o_fix.get("discount_total", 0)
        shipping_fee = o_fix.get("shipping_fee", 0)
        total = subtotal - discount_total + shipping_fee

        # Allocate discount
        for oi in order_items:
            line_val = oi.unit_price * oi.qty
            oi.allocated_discount = int((line_val * discount_total) / subtotal) if subtotal > 0 else 0

        p_status = PaymentStatus.PAID.value if o_fix.get("status") == "delivered" else PaymentStatus.UNPAID.value

        order = OrderModel(
            id=order_id,
            code=order_code,
            customer_id=owner_id,
            status=o_fix.get("status", "delivered"),
            payment_method=o_fix.get("payment_method", "card"),
            payment_status=p_status,
            subtotal=subtotal,
            discount_total=discount_total,
            shipping_fee=shipping_fee,
            total=total,
            paid_amount=total if p_status == PaymentStatus.PAID.value else 0,
            refunded_amount=0,
            channel="web",
            policy_version="2026-11-01",
            placed_at=placed_at,
            delivered_at=delivered_at,
        )
        session.add(order)
        for oi in order_items:
            session.add(oi)

        created_orders.append(order)

    await session.commit()
    return principal, created_orders


EVAL_DB_PATH = Path("evals/results/eval_fixtures.sqlite")


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


async def run_scenario(
    scenario: Scenario,
    agent_type: str = "oracle",
    langgraph_app: Any = None,
) -> ScenarioRunResult:
    """Execute a single scenario end-to-end and grade the result."""
    started = time.perf_counter()
    # 1. Reset tables in the dedicated evaluation database
    EVAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    eval_engine = get_eval_engine()
    eval_session_factory = async_sessionmaker(eval_engine, expire_on_commit=False, class_=AsyncSession)
    async with eval_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 2. Inject Clock
    clock_dt = datetime.fromisoformat(scenario.clock)
    clock = Clock(fixed_now=clock_dt)
    set_global_clock(clock)

    async with eval_session_factory() as session:
        principal, _ = await setup_scenario_fixtures(session, scenario, clock_dt)

        # 3. Setup Agent and Actors
        conversation_id = str(uuid.uuid4())
        scripted_user = ScriptedUser(scenario.user)
        staff_actor = StaffActor(scenario.staff)

        action_service = ActionService(session)

        agent: Any
        if agent_type == "oracle":
            agent = OracleAgent(session=session, principal=principal, scenario=scenario)
        elif agent_type == "null":
            agent = NullAgent(session=session)
        elif agent_type in ("langgraph", "main"):
            agent = LangGraphAgent(session=session, principal=principal, clock=clock_dt)
        else:
            agent = langgraph_app

        dialogue: list[dict[str, Any]] = []
        assistant_replies: list[str] = []
        all_tool_calls: list[dict[str, Any]] = []
        conversation_events: list[dict[str, Any]] = []

        last_assistant_text: str | None = None
        pending_action: dict[str, Any] | None = None

        max_turns = scenario.user.max_turns or 10

        for _turn_idx in range(max_turns):
            # User Turn
            user_say, action_decision, action_card = scripted_user.respond(
                assistant_text=last_assistant_text,
                pending_action=pending_action,
            )

            dialogue.append({"role": "customer", "content": user_say})

            # If user made an action decision on pending proposal
            if action_decision and pending_action:
                act_id = uuid.UUID(pending_action["id"])
                p_hash = pending_action["preview_hash"]
                if action_decision == "confirm":
                    await action_service.confirm_action(
                        action_id=act_id,
                        preview_hash=p_hash,
                        principal=principal,
                    )
                    conversation_events.append({"type": "action.confirmed", "action_id": str(act_id)})
                    # Process any approval requests created by confirmation
                    staff_notes = await staff_actor.step(session)
                    for sn in staff_notes:
                        conversation_events.append({"type": "staff.action", "note": sn})
                elif action_decision == "cancel":
                    await action_service.cancel_action(action_id=act_id, principal=principal)
                    conversation_events.append({"type": "action.cancelled", "action_id": str(act_id)})
                pending_action = None

            # Staff Step (e.g. approve gate A or packing cancel)
            staff_notes = await staff_actor.step(session)
            for sn in staff_notes:
                conversation_events.append({"type": "staff.action", "note": sn})

            # Agent Turn
            asst_text, tool_calls, proposed_action = await agent.step(
                conversation_id=conversation_id,
                user_message=user_say,
                dialogue_history=dialogue,
            )

            last_assistant_text = asst_text
            assistant_replies.append(asst_text)
            all_tool_calls.extend(tool_calls)
            dialogue.append({
                "role": "assistant",
                "content": asst_text,
                "tool_calls": tool_calls,
                "proposal": proposed_action,
            })

            if proposed_action:
                pending_action = proposed_action
                conversation_events.append({
                    "type": "action.proposed",
                    "action_id": proposed_action.get("id"),
                    "action_type": proposed_action.get("type"),
                })

            # If scenario reached end condition (user has no more steps and no pending action)
            if len(scripted_user._matched_steps) >= len(scenario.user.script) and not pending_action:
                break

        # Final Staff Step to ensure any triggered approvals are resolved
        await staff_actor.step(session)
        await session.commit()

        # 4. Grading
        db_passed, db_errors = await grade_db_state(session, scenario.expect.db)
        facts_passed, facts_errors = grade_required_facts(
            assistant_replies, scenario.expect.required_facts
        )
        tool_names = [tc.get("tool") or tc.get("name", "") for tc in all_tool_calls]
        forb_passed, forb_errors = grade_forbidden_patterns(
            assistant_replies, tool_names, scenario.expect.forbidden
        )
        inv_passed, inv_errors = check_safety_invariants(
            all_tool_calls, conversation_events, assistant_replies
        )

        tools_passed, tools_errors = grade_tool_execution(
            tool_calls=all_tool_calls,
            required_tools=scenario.expect.required_tools,
            required_args=scenario.expect.required_tool_args,
            ordering_constraints=scenario.expect.tool_ordering,
        )

        all_errors = db_errors + facts_errors + forb_errors + tools_errors + inv_errors
        passed = db_passed and facts_passed and forb_passed and inv_passed and tools_passed

        return ScenarioRunResult(
            scenario_id=scenario.id,
            passed=passed,
            db_passed=db_passed,
            facts_passed=facts_passed,
            forbidden_passed=forb_passed,
            invariants_passed=inv_passed,
            tool_calls_count=len(all_tool_calls),
            turns_count=len(dialogue) // 2,
            fallback_turns=scripted_user.fallback_turns,
            errors=all_errors,
            safety_violations=inv_errors,
            dialogue=dialogue,
            tags=list(scenario.tags),
            tool_score=score_tool_use(
                all_tool_calls,
                required_tools=scenario.expect.required_tools,
                required_args=scenario.expect.required_tool_args,
                ordering_constraints=scenario.expect.tool_ordering,
            ),
            duration_s=round(time.perf_counter() - started, 2),
            usage=dict(getattr(agent, "usage", {})),
            tool_calls=all_tool_calls,
        )


async def run_eval_cli(
    agent: str = "oracle",
    group: str = "all",
    mode: str = "offline",
    tag: str = "smoke",
    k: int = 1,
    gate: bool = False,
    out_dir: Path | None = None,
) -> tuple[EvalSummary, list[dict[str, Any]]]:
    """Run scenarios, save raw trajectories and gate table; return the summary and gate rows."""
    scenario_files = sorted(Path("evals/scenarios").glob("*.yaml"))
    scenarios: list[Scenario] = []
    for f in scenario_files:
        sc = load_scenario_from_yaml(f)
        if group != "all" and not sc.group.startswith(group):
            continue
        if tag and tag != "all" and tag not in sc.tags:
            continue
        scenarios.append(sc)

    print(f"Bắt đầu đánh giá: {len(scenarios)} kịch bản | agent={agent} | group={group} | mode={mode} | k={k}", flush=True)

    all_runs: dict[str, list[ScenarioRunResult]] = {}
    for sc in scenarios:
        all_runs[sc.id] = []
        for run_idx in range(k):
            res = await run_scenario(scenario=sc, agent_type=agent)
            all_runs[sc.id].append(res)
            status_str = "PASS" if res.passed else "FAIL"
            err_str = f" | Lỗi: {res.errors}" if not res.passed else ""
            print(
                f"[{status_str}] {sc.id} (lần {run_idx+1}/{k}) | turns={res.turns_count} | "
                f"tools={res.tool_calls_count} | {res.duration_s}s{err_str}",
                flush=True,
            )

    summary = compute_eval_metrics(all_runs, k_values=list(range(1, k + 1)))
    every_run = [r for runs in all_runs.values() for r in runs]
    gate_rows = evaluate_gates(compute_gate_metrics(every_run), load_gates())

    run_id = f"{agent}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    target = out_dir or Path("evals/results") / run_id
    save_run_artifacts(
        target,
        every_run,
        gate_rows,
        {"agent": agent, "k": k, "scenarios": len(scenarios), "group": group, "tag": tag, "run_id": run_id},
    )

    print("-" * 60)
    print("KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN:")
    print(f"Tổng số kịch bản: {summary.total_scenarios}")
    for kv, rate in summary.pass_k.items():
        print(f"pass^{kv}: {rate:.1f}%")
    print(f"Tỉ lệ đạt theo nhóm: {summary.group_pass_rates}")
    print(f"Số vi phạm an toàn: {summary.safety_violations_count}")
    print(f"Tỉ lệ câu thoái thác: {summary.average_fallback_rate:.1f}%")
    for row in gate_rows:
        value = "n/a" if row["value"] is None else f"{row['value']:.3f}"
        print(f"GATE {row['status']:12} {row['metric']:36} {value} (ngưỡng {row['threshold']}, mẫu {row['numerator']}/{row['denominator']})")
    print(f"Artifact: {target}")
    print("-" * 60)
    if gate and any(row["status"] != "PASS" for row in gate_rows):
        print("QUALITY GATE: FAILED hoặc NOT VERIFIED", flush=True)
    return summary, gate_rows


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run Shop Support Agent Evaluation Suite")
    parser.add_argument("--agent", choices=["oracle", "null", "langgraph"], default="oracle", help="Agent implementation")
    parser.add_argument("-k", "--k", type=int, default=1, help="Independent runs per scenario")
    parser.add_argument("--group", default="all", help="Scenario group filter")
    parser.add_argument("--tag", default="all", help="Scenario tag filter")
    parser.add_argument("--gate", action="store_true", help="Exit 1 unless every quality gate PASSes")
    parser.add_argument("--out", type=Path, default=None, help="Directory for raw trajectories and the gate table")
    args = parser.parse_args()

    _, rows = asyncio.run(
        run_eval_cli(agent=args.agent, k=args.k, group=args.group, tag=args.tag, gate=args.gate, out_dir=args.out)
    )
    sys.exit(1 if args.gate and any(row["status"] != "PASS" for row in rows) else 0)
