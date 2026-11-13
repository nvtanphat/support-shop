"""Regression tests: tool-first enforcement, loop termination and slot grounding.

The model is a scripted stand-in, so these tests prove the orchestration around the model
(mock tests). They say nothing about Gemini quality, which is measured by the real-LLM eval.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from shopagent.agent.nodes import agent as agent_module
from shopagent.agent.nodes.agent import LoopBudget, agent_node
from shopagent.agent.nodes.load_context import load_context_node
from shopagent.agent.nodes.persist_emit import _history_message_for
from shopagent.agent.nodes.verify_output import verify_output_node
from shopagent.agent.slot_guard import GroundingContext, find_ungrounded_slot
from shopagent.agent.state import AgentState
from shopagent.agent.tool_requirements import derive_requirements, unmet_requirements
from shopagent.core.clock import get_clock
from shopagent.core.principal import Principal
from shopagent.infra.db.tables import Base, TicketModel
from shopagent.rag.indexer import index_policies
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ESCALATE_ARGS = {"reason_code": "customer_request", "summary": "Khách yêu cầu gặp nhân viên hỗ trợ"}


def tool_call_msg(name: str, args: dict[str, Any], call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class ScriptedModel:
    """Returns queued responses in order; an Exception in the queue is raised instead."""

    def __init__(self, script: list[AIMessage | Exception]) -> None:
        self.script = list(script)
        self.calls = 0

    def bind_tools(self, tools: list[Any]) -> ScriptedModel:
        return self

    async def ainvoke(self, messages: list[Any], **_: Any) -> AIMessage:
        self.calls += 1
        if not self.script:
            raise AssertionError("scripted model exhausted: agent called the LLM more often than expected")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant(_: float) -> None:
        return None

    monkeypatch.setattr(agent_module.asyncio, "sleep", _instant)


def use_model(monkeypatch: pytest.MonkeyPatch, model: ScriptedModel) -> None:
    monkeypatch.setattr(agent_module, "get_chat_model", lambda role="agent_primary": model)


def use_budget(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
    base = LoopBudget.from_config()
    values = {**base.__dict__, **overrides}
    monkeypatch.setattr(LoopBudget, "from_config", classmethod(lambda cls: LoopBudget(**values)))


def make_state(text: str, *, principal: Principal | None = None, **extra: Any) -> AgentState:
    return {
        "conversation_id": str(uuid.uuid4()),
        "messages": [HumanMessage(content=text, id=f"h-{uuid.uuid4()}")],
        "principal": principal or Principal.guest(),
        "clock": get_clock().now(),
        **extra,
    }


def run_config(session: AsyncSession) -> dict[str, Any]:
    return {"configurable": {"session": session}}


# ---------------------------------------------------------------------------
# Tool-first enforcement
# ---------------------------------------------------------------------------
def test_requirements_follow_intent_and_skip_unneeded_tools() -> None:
    tools = {"search_policy", "get_order", "escalate_to_human"}
    assert derive_requirements("Xin chào shop", tools) == []
    assert [r.key for r in derive_requirements("Cho mình gặp nhân viên với", tools)] == ["escalate"]
    assert [r.key for r in derive_requirements("Đơn sl-123456 đang ở đâu?", tools)] == ["order:SL-123456"]
    assert [r.key for r in derive_requirements("Chính sách đổi trả thế nào?", tools)] == ["policy"]
    # An order-specific policy question needs both the order data and policy evidence.
    assert [r.key for r in derive_requirements("Đơn SL-1 có được đổi không?", tools)] == ["order:SL-1", "policy"]


def test_guest_order_requirement_prefers_guest_lookup() -> None:
    reqs = derive_requirements("Kiểm tra đơn SL-77", {"lookup_order_guest", "search_policy", "escalate_to_human"})
    assert reqs[0].preferred_tool == "lookup_order_guest"


def test_order_requirement_needs_matching_order_code_and_real_execution() -> None:
    reqs = derive_requirements("Đơn SL-1 đâu rồi", {"get_order"})
    wrong_order = [{"tool": "get_order", "args": {"order_code": "SL-2"}, "result": {}}]
    timed_out = [{"tool": "get_order", "args": {"order_code": "SL-1"}, "result": {"error_code": "TOOL_TIMEOUT"}}]
    done = [{"tool": "get_order", "args": {"order_code": "sl-1"}, "result": {"status": "delivered"}}]
    assert unmet_requirements(reqs, wrong_order)
    assert unmet_requirements(reqs, timed_out)
    assert unmet_requirements(reqs, done) == []


@pytest.mark.asyncio
async def test_verbal_escalation_promise_is_steered_into_a_real_tool_call(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedModel(
        [
            AIMessage(content="Dạ em sẽ chuyển cho chuyên viên ngay ạ."),
            tool_call_msg("escalate_to_human", ESCALATE_ARGS),
            AIMessage(content="Phiếu hỗ trợ đã được tạo, chuyên viên sẽ liên hệ quý khách sớm ạ."),
        ]
    )
    use_model(monkeypatch, model)
    state = make_state("Cho mình gặp nhân viên hỗ trợ")
    out = await agent_node(state, run_config(session))

    assert out["turn_status"] == "completed"
    assert [c["tool"] for c in out["tool_calls"]] == ["escalate_to_human"]
    assert "ticket_code" in out["tool_calls"][0]["result"]
    assert (await session.execute(select(TicketModel))).scalars().all()
    # The unfulfilled promise must not enter persisted history.
    texts = [str(m.content) for m in out["messages"] if isinstance(m, AIMessage)]
    assert not any("sẽ chuyển cho chuyên viên ngay" in t for t in texts)
    verified = verify_output_node({**state, **out, "messages": [*state["messages"], *out["messages"]]})
    assert "error" not in verified


@pytest.mark.asyncio
async def test_draft_citing_an_unlooked_up_clause_is_steered_instead_of_blocked(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seen live: the reply cited [POL-RETURN-01] without a lookup, verify_output blocked it and the customer got a refusal."""
    model = ScriptedModel(
        [
            AIMessage(content="Theo [POL-RETURN-01], hàng lỗi được trả trong 15 ngày."),
            AIMessage(content="Mình chưa tra cứu điều khoản nên chưa thể nêu thời hạn cụ thể, bạn cho mình biết mã đơn nhé."),
        ]
    )
    use_model(monkeypatch, model)
    state = make_state("Hàng bị lỗi thì sao")
    out = await agent_node(state, run_config(session))

    assert out["turn_status"] == "completed" and model.calls == 2
    texts = [str(m.content) for m in out["messages"] if isinstance(m, AIMessage)]
    assert not any("POL-RETURN-01" in t for t in texts)  # the unsupported draft never enters history
    verified = verify_output_node({**state, **out, "messages": [*state["messages"], *out["messages"]]})
    assert "error" not in verified


def test_unretrieved_citations_ignores_clauses_that_were_looked_up() -> None:
    from shopagent.agent.tool_requirements import unretrieved_citations

    assert unretrieved_citations("Theo [POL-A-01] và [POL-B-02].", ["POL-A-01"]) == ["POL-B-02"]
    assert unretrieved_citations("Không trích dẫn gì.", []) == []


@pytest.mark.asyncio
async def test_model_that_never_calls_required_tool_gets_no_promise_through(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    promise = AIMessage(content="Em đã chuyển thông tin cho chuyên viên rồi ạ.")
    model = ScriptedModel([promise, promise, promise])
    use_model(monkeypatch, model)
    state = make_state("Cho mình nói chuyện với người thật")
    out = await agent_node(state, run_config(session))

    assert out["turn_status"] == "requirements_unmet"
    assert out["unmet_requirements"] == ["escalate"]
    assert out["messages"] == []
    verified = verify_output_node({**state, **out})
    assert "chuyển thông tin" not in verified["verified_output"]
    assert "TURN_NOT_COMPLETED" in verified["error"]


@pytest.mark.asyncio
async def test_greeting_calls_no_tool(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    model = ScriptedModel([AIMessage(content="Dạ ShopLab xin chào quý khách ạ.")])
    use_model(monkeypatch, model)
    out = await agent_node(make_state("Xin chào"), run_config(session))
    assert out["turn_status"] == "completed"
    assert out["tool_calls"] == []
    assert model.calls == 1


# ---------------------------------------------------------------------------
# Loop termination
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_calls_on_last_iteration_are_synthesized(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedModel(
        [
            tool_call_msg("search_policy", {"query": "đổi trả hàng lỗi"}),
            AIMessage(content="Theo điều khoản đã tra cứu, hàng lỗi được đổi trả ạ."),
        ]
    )
    use_model(monkeypatch, model)
    use_budget(monkeypatch, max_iterations=1)
    await index_policies(session)
    state = make_state("Chính sách đổi trả hàng lỗi thế nào?")
    out = await agent_node(state, run_config(session))

    assert out["turn_status"] == "synthesized"
    final = out["messages"][-1]
    assert isinstance(final, AIMessage) and final.content and not final.tool_calls
    # Every tool call has a matching ToolMessage: no tool result is dropped.
    call_ids = {c["id"] for m in out["messages"] if isinstance(m, AIMessage) for c in m.tool_calls}
    result_ids = {m.tool_call_id for m in out["messages"] if isinstance(m, ToolMessage)}
    assert call_ids == result_ids


@pytest.mark.asyncio
async def test_failed_synthesis_is_degraded_not_an_empty_success(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedModel(
        [tool_call_msg("search_policy", {"query": "đổi trả hàng lỗi"}), RuntimeError("llm down")]
    )
    use_model(monkeypatch, model)
    use_budget(monkeypatch, max_iterations=1)
    state = make_state("Chính sách đổi trả hàng lỗi thế nào?")
    out = await agent_node(state, run_config(session))

    assert out["turn_status"] == "degraded"
    verified = verify_output_node({**state, **out, "messages": [*state["messages"], *out["messages"]]})
    assert verified["verified_output"].strip()
    assert "TURN_NOT_COMPLETED" in verified["error"]


@pytest.mark.asyncio
async def test_llm_outage_degrades_after_bounded_retries(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    model = ScriptedModel([RuntimeError("503 UNAVAILABLE")] * 4)
    use_model(monkeypatch, model)
    out = await agent_node(make_state("Xin chào"), run_config(session))
    assert out["turn_status"] == "degraded"
    assert model.calls == 4  # 3 primary attempts (2 retries with backoff) + 1 fallback attempt


@pytest.mark.asyncio
async def test_turn_deadline_stops_the_loop(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    model = ScriptedModel([])
    use_model(monkeypatch, model)
    use_budget(monkeypatch, turn_timeout_s=-1.0)
    out = await agent_node(make_state("Xin chào"), run_config(session))
    assert out["turn_status"] == "degraded"
    assert model.calls == 0


def test_verify_rejects_assistant_message_with_pending_tool_calls() -> None:
    state: AgentState = {
        "messages": [HumanMessage(content="hi"), tool_call_msg("search_policy", {"query": "x y"})],
        "turn_status": "completed",
    }
    res = verify_output_node(state)
    assert res["verified_output"].strip()
    assert "TURN_NOT_COMPLETED" in res["error"]


def test_verify_never_reuses_previous_turn_answer_when_turn_is_degraded() -> None:
    state: AgentState = {
        "messages": [AIMessage(content="Câu trả lời của lượt trước"), HumanMessage(content="lượt mới")],
        "turn_status": "degraded",
    }
    assert "lượt trước" not in verify_output_node(state)["verified_output"]


# ---------------------------------------------------------------------------
# Missing information / slot grounding
# ---------------------------------------------------------------------------
ORDER_RESULT = (
    '{"code": "SL-100002", "items": [{"item_id": "11111111-aaaa", "product_name": "Áo sơ mi"},'
    ' {"item_id": "22222222-bbbb", "product_name": "Quần jean"}]}'
)


def grounding(user_texts: list[str], tool_texts: list[str] | None = None, recent: list[str] | None = None) -> GroundingContext:
    msgs: list[Any] = [HumanMessage(content=t) for t in user_texts]
    msgs += [ToolMessage(content=t, tool_call_id=f"t{i}") for i, t in enumerate(tool_texts or [])]
    return GroundingContext(msgs, recent or [])


def test_guessed_order_code_is_rejected() -> None:
    res = find_ungrounded_slot("get_order", {"order_code": "SL-999999"}, grounding(["Mình muốn trả hàng"]))
    assert res and res["error_code"] == "MISSING_SLOT" and res["slot"] == "order_code"


def test_order_code_from_customer_words_or_recent_orders_is_accepted() -> None:
    assert find_ungrounded_slot("get_order", {"order_code": "sl-100002"}, grounding(["đơn SL-100002"])) is None
    # "đơn thứ hai" resolved by the model against the database-backed recent-orders list.
    assert find_ungrounded_slot("get_order", {"order_code": "SL-100002"}, grounding(["đơn thứ hai"], recent=["SL-100001", "SL-100002"])) is None


def test_item_must_come_from_get_order_result() -> None:
    args = {"order_code": "SL-100002", "item_ids": ["invented-id"], "reason_code": "defective"}
    g = grounding(["đơn SL-100002 cái áo bị rách"], [ORDER_RESULT])
    res = find_ungrounded_slot("check_return_eligibility", args, g)
    assert res and res["slot"] == "item_ids"
    ok = {**args, "item_ids": ["11111111-aaaa"]}
    assert find_ungrounded_slot("check_return_eligibility", ok, g) is None


def test_invalid_reason_and_missing_exchange_sku_are_rejected() -> None:
    g = grounding(["đơn SL-100002 cái áo mình đổi ý"], [ORDER_RESULT])
    base = {"order_code": "SL-100002", "items": [{"item_id": "11111111-aaaa", "qty": 1}]}
    assert find_ungrounded_slot("propose_return", {**base, "reason_code": "khong_thich"}, g)["slot"] == "reason_code"
    exchange = {**base, "reason_code": "change_of_mind", "resolution": "exchange"}
    assert find_ungrounded_slot("propose_return", exchange, g)["slot"] == "exchange_sku"
    checked = '{"eligible": true, "checked": {"order_code": "SL-100002", "item_ids": ["11111111-aaaa"], "reason_code": "change_of_mind", "resolution": "exchange"}}'
    g_checked = grounding(["đơn SL-100002 cái áo mình đổi ý"], [ORDER_RESULT, checked])
    assert find_ungrounded_slot("propose_return", {**exchange, "exchange_sku": "TS-M"}, g_checked) is None


@pytest.mark.asyncio
async def test_agent_does_not_execute_tool_with_guessed_order_code(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = ScriptedModel(
        [
            tool_call_msg("lookup_order_guest", {"order_code": "SL-999999"}),
            AIMessage(content="Quý khách vui lòng cho em xin mã đơn hàng cần tra cứu ạ."),
        ]
    )
    use_model(monkeypatch, model)
    out = await agent_node(make_state("Mình muốn kiểm tra đơn hàng"), run_config(session))
    assert out["turn_status"] == "completed"
    assert out["tool_calls"][0]["result"]["error_code"] == "MISSING_SLOT"


# ---------------------------------------------------------------------------
# Context and memory
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_context_resets_all_per_turn_state(session: AsyncSession) -> None:
    stale: AgentState = make_state(
        "lượt mới",
        retrieved_clauses=["POL-OLD-01"],
        tool_calls=[{"tool": "get_order"}],
        turn_status="degraded",
        unmet_requirements=["escalate"],
        verified_output="câu trả lời cũ",
        error="lỗi cũ",
    )
    out = await load_context_node(stale, run_config(session))
    assert out["retrieved_clauses"] == []
    assert out["tool_calls"] == []
    assert out["verified_output"] is None and out["error"] is None
    assert out["unmet_requirements"] == []
    assert out["dynamic_context"]["policy_version"]


def test_history_matches_what_customer_saw() -> None:
    human = HumanMessage(content="hi", id="h1")
    final = AIMessage(content="nháp chưa kiểm chứng", id="a1")
    replaced = _history_message_for([human, final], "bản đã xác minh")
    assert replaced is not None and replaced.id == "a1" and replaced.content == "bản đã xác minh"
    assert _history_message_for([human, final], "nháp chưa kiểm chứng") is None
    # Degraded turn: no final assistant message exists, so the safe reply is appended.
    appended = _history_message_for([final, human], "câu an toàn")
    assert appended is not None and appended.id != "a1"
    pending = tool_call_msg("search_policy", {"query": "x y"})
    assert _history_message_for([human, pending], "câu an toàn").content == "câu an toàn"


def test_reason_the_customer_never_expressed_is_rejected() -> None:
    g = grounding(["Mình muốn trả cái áo trong đơn SL-100002"], [ORDER_RESULT])
    args = {"order_code": "SL-100002", "item_ids": ["11111111-aaaa"], "reason_code": "defective"}
    res = find_ungrounded_slot("check_return_eligibility", args, g)
    assert res and res["slot"] == "reason_code"
    said = grounding(["Mình muốn trả cái áo trong đơn SL-100002", "bị rách chỉ"], [ORDER_RESULT])
    assert find_ungrounded_slot("check_return_eligibility", args, said) is None
    # A reason word for another code does not license this code.
    wrong = {**args, "reason_code": "change_of_mind"}
    assert find_ungrounded_slot("check_return_eligibility", wrong, said)["slot"] == "reason_code"


def test_item_in_multi_item_order_must_be_named_by_customer() -> None:
    args = {"order_code": "SL-100002", "item_ids": ["11111111-aaaa"], "reason_code": "defective"}
    vague = grounding(["Đơn SL-100002 bị lỗi, mình muốn trả"], [ORDER_RESULT])
    assert find_ungrounded_slot("check_return_eligibility", args, vague)["slot"] == "item_ids"
    named = grounding(["Đơn SL-100002 cái áo bị lỗi, mình muốn trả"], [ORDER_RESULT])
    assert find_ungrounded_slot("check_return_eligibility", args, named) is None


# ---------------------------------------------------------------------------
# Tool outcomes: called is not succeeded, succeeded is not evidence for a refusal
# ---------------------------------------------------------------------------
def test_outcome_classification_never_treats_errors_as_success() -> None:
    from shopagent.agent.tool_requirements import ToolOutcome, classify_result

    assert classify_result({"order_code": "SL-1", "status": "delivered"}) is ToolOutcome.SUCCEEDED
    assert classify_result({"error_code": "ORDER_NOT_FOUND"}) is ToolOutcome.DEFINITIVE_NEGATIVE
    assert classify_result({"status": "no_evidence", "results": []}) is ToolOutcome.DEFINITIVE_NEGATIVE
    for failed in (
        {"error_code": "TOOL_TIMEOUT"},
        {"error_code": "MISSING_SLOT"},
        {"error_code": "SOMETHING_NEW"},
        {"status": "db_error", "error_code": "POLICY_DB_ERROR"},
        {"status": "index_unavailable"},
        None,
        "",
    ):
        assert classify_result(failed) is ToolOutcome.FAILED, failed


def test_not_found_order_may_be_explained_but_failed_lookup_may_not() -> None:
    reqs = derive_requirements("Đơn SL-9 đâu rồi", {"get_order"})
    not_found = [{"tool": "get_order", "args": {"order_code": "SL-9"}, "result": {"error_code": "ORDER_NOT_FOUND"}}]
    db_down = [{"tool": "get_order", "args": {"order_code": "SL-9"}, "result": {"error_code": "TOOL_EXECUTION_ERROR"}}]
    assert unmet_requirements(reqs, not_found) == []
    assert unmet_requirements(reqs, db_down)


def test_policy_lookup_failure_blocks_answer_but_honest_no_evidence_is_allowed() -> None:
    reqs = derive_requirements("Chính sách đổi trả thế nào?", {"search_policy"})
    empty = [{"tool": "search_policy", "args": {"query": "x"}, "result": {"status": "no_evidence", "results": []}}]
    db_down = [{"tool": "search_policy", "args": {"query": "x"}, "result": {"status": "db_error", "error_code": "POLICY_DB_ERROR"}}]
    found = [{"tool": "search_policy", "args": {"query": "x"}, "result": {"status": "success", "results": [{"clause_id": "POL-RETURN-01"}]}}]
    assert unmet_requirements(reqs, db_down)
    assert unmet_requirements(reqs, empty) == []
    assert unmet_requirements(reqs, found) == []


# ---------------------------------------------------------------------------
# Duplicate proposals
# ---------------------------------------------------------------------------
def test_second_proposal_in_one_turn_is_refused() -> None:
    from shopagent.agent.proposal_guard import find_proposal_conflict

    done = [{"tool": "propose_return", "args": {}, "result": {"action_id": "a1", "type": "return_request"}}]
    assert find_proposal_conflict("propose_cancel_order", done, None)["error_code"] == "PROPOSAL_ALREADY_CREATED"
    assert find_proposal_conflict("get_order", done, None) is None
    failed = [{"tool": "propose_return", "args": {}, "result": {"error_code": "ORDER_NOT_FOUND"}}]
    assert find_proposal_conflict("propose_return", failed, None) is None


def test_live_card_of_the_same_kind_blocks_a_new_one_but_not_another_kind() -> None:
    from shopagent.agent.proposal_guard import find_proposal_conflict

    active = {"type": "return_request", "code": "ab12cd34"}
    blocked = find_proposal_conflict("propose_return", [], active)
    assert blocked["error_code"] == "PENDING_ACTION_EXISTS" and blocked["existing_action_code"] == "ab12cd34"
    assert find_proposal_conflict("propose_cancel_order", [], active) is None


# ---------------------------------------------------------------------------
# Context window
# ---------------------------------------------------------------------------
def test_current_turn_is_kept_whole_even_when_a_tool_result_is_huge() -> None:
    from shopagent.agent.context_window import prune_messages_token_aware

    huge = ToolMessage(content="x" * 60000, tool_call_id="c1", name="get_order")
    history = [
        HumanMessage(content="câu cũ " * 50),
        AIMessage(content="trả lời cũ " * 50),
        HumanMessage(content="Đơn SL-1 sao rồi?"),
        tool_call_msg("get_order", {"order_code": "SL-1"}),
        huge,
    ]
    pruned = prune_messages_token_aware(history, max_input_tokens=500)
    assert pruned[0].content == "Đơn SL-1 sao rồi?"  # the question survives, old history is dropped
    assert pruned[-1] is huge and len(pruned) == 3


def test_reserved_tokens_shrink_the_room_for_history_without_splitting_pairs() -> None:
    from shopagent.agent.context_window import prune_messages_token_aware

    old = [
        HumanMessage(content="a " * 200),
        tool_call_msg("search_policy", {"query": "x y"}, call_id="c0"),
        ToolMessage(content="r " * 200, tool_call_id="c0", name="search_policy"),
        AIMessage(content="đã trả lời"),
    ]
    now = [HumanMessage(content="câu mới")]
    roomy = prune_messages_token_aware([*old, *now], max_input_tokens=3000, reserved_tokens=0)
    tight = prune_messages_token_aware([*old, *now], max_input_tokens=3000, reserved_tokens=2900)
    assert len(roomy) == 5
    assert tight == now  # nothing left over for history
    for kept in (roomy, tight):
        ids = {c["id"] for m in kept if isinstance(m, AIMessage) for c in m.tool_calls}
        assert ids == {m.tool_call_id for m in kept if isinstance(m, ToolMessage)}


def test_propose_return_must_follow_a_matching_positive_eligibility_check() -> None:
    args = {"order_code": "SL-100002", "items": [{"item_id": "11111111-aaaa", "qty": 1}], "reason_code": "defective"}
    said = ["đơn SL-100002 cái áo bị rách"]

    def check(eligible: bool, **overrides: object) -> str:
        checked = {"order_code": "SL-100002", "item_ids": ["11111111-aaaa"], "reason_code": "defective", **overrides}
        return json.dumps({"eligible": eligible, "checked": checked})

    never = grounding(said, [ORDER_RESULT])
    assert find_ungrounded_slot("propose_return", args, never)["error_code"] == "ELIGIBILITY_NOT_CHECKED"
    other_order = grounding(said, [ORDER_RESULT, check(True, order_code="SL-OTHER")])
    assert find_ungrounded_slot("propose_return", args, other_order)["error_code"] == "ELIGIBILITY_NOT_CHECKED"
    other_reason = grounding(said, [ORDER_RESULT, check(True, reason_code="change_of_mind")])
    assert find_ungrounded_slot("propose_return", args, other_reason)["error_code"] == "ELIGIBILITY_NOT_CHECKED"
    refused = grounding(said, [ORDER_RESULT, check(False)])
    assert find_ungrounded_slot("propose_return", args, refused)["error_code"] == "NOT_ELIGIBLE"
    ok = grounding(said, [ORDER_RESULT, check(True)])
    assert find_ungrounded_slot("propose_return", args, ok) is None


@pytest.mark.asyncio
async def test_transient_errors_back_off_and_recover_but_bad_requests_are_not_retried(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []

    async def record(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(agent_module.asyncio, "sleep", record)
    flaky = ScriptedModel(
        [RuntimeError("503 UNAVAILABLE: high demand"), RuntimeError("504 DEADLINE_EXCEEDED"), AIMessage(content="Dạ xin chào ạ.")]
    )
    use_model(monkeypatch, flaky)
    out = await agent_node(make_state("Xin chào"), run_config(session))
    assert out["turn_status"] == "completed" and delays == [1.0, 3.0]

    delays.clear()
    bad = ScriptedModel([RuntimeError("400 INVALID_ARGUMENT: bad schema")] * 3)
    use_model(monkeypatch, bad)
    out = await agent_node(make_state("Xin chào"), run_config(session))
    assert out["turn_status"] == "degraded" and delays == [] and bad.calls == 2  # one try + the fallback model


@pytest.mark.asyncio
async def test_agent_turn_survives_a_proposal_blocked_for_missing_eligibility_check(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration of the guard with the loop: the blocked call is a tool result, never a crash."""
    customer = Principal.customer(customer_id=uuid.uuid4(), email="c@example.com")
    state = make_state(
        "đơn SL-100002 cái áo bị rách, mình muốn trả",
        principal=customer,
    )
    state["messages"] = [
        *state["messages"],
        tool_call_msg("get_order", {"order_code": "SL-100002"}, call_id="g1"),
        ToolMessage(content=ORDER_RESULT, tool_call_id="g1", name="get_order"),
    ]
    propose = {
        "order_code": "SL-100002",
        "items": [{"item_id": "11111111-aaaa", "qty": 1}],
        "reason_code": "defective",
    }
    model = ScriptedModel(
        [tool_call_msg("propose_return", propose, call_id="p1"), *[AIMessage(content="Dạ em kiểm tra điều kiện trước ạ.")] * 4]
    )
    use_model(monkeypatch, model)
    out = await agent_node(state, run_config(session))
    blocked = [c for c in out["tool_calls"] if c["tool"] == "propose_return"]
    assert blocked and blocked[0]["result"]["error_code"] == "ELIGIBILITY_NOT_CHECKED"
    assert blocked[0]["outcome"] == "failed"
    # The order lookup happened in an earlier turn, so this turn is steered for a fresh one; whatever the
    # final status, the blocked proposal must not have created a card or crashed the node.
    assert out["turn_status"] in ("completed", "requirements_unmet") and "pending_action" not in out


def test_rate_limit_hint_sets_the_wait_within_bounds() -> None:
    from shopagent.agent.nodes.agent import _retry_wait_s

    hinted = RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 12.4s.")
    assert _retry_wait_s(hinted, 1.0) == pytest.approx(13.4)
    assert _retry_wait_s(RuntimeError("429 ... retry in 600s"), 1.0) == 20.0  # bounded
    assert _retry_wait_s(RuntimeError("503 UNAVAILABLE"), 3.0) == 3.0  # no hint: the configured backoff
    assert _retry_wait_s(RuntimeError("retry in 0.5s"), 3.0) == 3.0  # never shorter than the backoff
