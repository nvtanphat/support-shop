"""Grounding across turns: who chose the order, what the customer said the problem was, and what already happened.

Each test pins a failure seen in real Gemini runs:
- a cancel card was proposed for the newest of two orders the customer never chose;
- a clearly described defect ("bị rè một bên tai") could only be accepted after a yes/no question;
- a ticket or a confirmed return from an earlier turn counted as no evidence, so true replies were blocked;
- every follow-up message opened another support ticket;
- "bấm nút Xác nhận" was not recognised as pointing at a card.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from shopagent.agent.grounding import check_claims
from shopagent.agent.nodes.load_context import load_context_node
from shopagent.agent.nodes.verify_output import verify_output_node
from shopagent.agent.slot_guard import GroundingContext, find_ungrounded_slot
from shopagent.core.clock import Clock, get_clock, set_global_clock
from shopagent.core.principal import Principal
from shopagent.domain.services.tickets import TicketService
from shopagent.infra.db.tables import (
    Base,
    CustomerModel,
    OrderModel,
    PendingActionModel,
    ReturnRequestModel,
    TicketModel,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def _ctx(*turns: tuple[str, str], recent: tuple[str, ...] = ()) -> GroundingContext:
    messages: list[BaseMessage] = []
    for who, text in turns:
        if who == "customer":
            messages.append(HumanMessage(content=text))
        elif who == "assistant":
            messages.append(AIMessage(content=text))
        else:
            messages.append(ToolMessage(content=text, tool_call_id=str(uuid.uuid4())))
    return GroundingContext(messages, list(recent))


# --- A write proposal acts on the order the customer chose --------------------------------------------------
_TWO = ("SL-A00001", "SL-B00002")


@pytest.mark.parametrize("tool", ["propose_cancel_order", "propose_return", "check_return_eligibility"])
def test_with_two_recent_orders_a_proposal_needs_the_customer_to_choose_one(tool: str) -> None:
    ctx = _ctx(("customer", "Cho mình hủy đơn với"), recent=_TWO)
    result = find_ungrounded_slot(tool, {"order_code": "SL-A00001"}, ctx)
    assert result is not None and result["slot"] == "order_code"


@pytest.mark.parametrize(
    ("turns", "why"),
    [
        ((("customer", "Hủy giúp mình đơn SL-A00001"),), "the customer typed the code"),
        ((("customer", "Hủy đơn gần nhất giúp mình"),), "a reference to the recent-orders list"),
        ((("customer", "Mình muốn hủy đơn thứ nhất"),), "an ordinal into the recent-orders list"),
        ((("customer", "Cho mình hủy đơn với"), ("assistant", "Bạn muốn hủy đơn SL-A00001 phải không ạ?"), ("customer", "Đúng rồi")),
         "a yes to a question naming that order"),
    ],
)
def test_a_chosen_order_can_be_proposed(turns: tuple[tuple[str, str], ...], why: str) -> None:
    assert find_ungrounded_slot("propose_cancel_order", {"order_code": "SL-A00001"}, _ctx(*turns, recent=_TWO)) is None, why


def test_a_yes_about_one_order_does_not_choose_another() -> None:
    ctx = _ctx(("customer", "Cho mình hủy đơn với"), ("assistant", "Bạn muốn hủy đơn SL-A00001 phải không ạ?"), ("customer", "Đúng rồi"),
               recent=_TWO)
    assert find_ungrounded_slot("propose_cancel_order", {"order_code": "SL-B00002"}, ctx) is not None


def test_a_single_recent_order_is_the_one_meant() -> None:
    ctx = _ctx(("customer", "Cho mình hủy đơn với"), recent=("SL-A00001",))
    assert find_ungrounded_slot("propose_cancel_order", {"order_code": "SL-A00001"}, ctx) is None


def test_reading_an_order_from_the_recent_list_needs_no_choice() -> None:
    ctx = _ctx(("customer", "Đơn của mình sao rồi"), recent=_TWO)
    assert find_ungrounded_slot("get_order", {"order_code": "SL-A00001"}, ctx) is None


# --- A reason may be grounded by the customer's own words, quoted -------------------------------------------
_HEADPHONES = json.dumps({"items": [{"item_id": "it-1", "product_name": "tai nghe"}]}, ensure_ascii=False)
_DRESS = json.dumps({"items": [{"item_id": "it-1", "product_name": "váy"}]}, ensure_ascii=False)


def _check(reason: str, quote: str | None, said: str, items: str = _HEADPHONES) -> dict[str, Any] | None:
    args: dict[str, Any] = {"order_code": "SL-A00001", "item_ids": ["it-1"], "reason_code": reason}
    if quote is not None:
        args["reason_quote"] = quote
    return find_ungrounded_slot("check_return_eligibility", args, _ctx(("customer", said), ("tool", items)))


_SAID = "Tai nghe mua ở đơn SL-A00001 bị rè một bên tai, mình muốn trả"


def test_a_described_symptom_quoted_verbatim_grounds_the_reason() -> None:
    assert _check("defective", "bị rè một bên tai", _SAID) is None


@pytest.mark.parametrize(
    ("reason", "quote", "said", "items", "why"),
    [
        ("defective", "tai nghe hỏng rồi", _SAID, _HEADPHONES, "not what the customer wrote"),
        ("defective", "mình muốn trả", _SAID, _HEADPHONES, "a request to return describes no problem"),
        ("defective", "cái váy", "Mình muốn trả cái váy đơn SL-A00001", _DRESS, "the product name is not a problem"),
        ("defective", "mặc không vừa", "Váy đơn SL-A00001 mặc không vừa", _DRESS, "the words state a change of mind"),
        ("defective", None, _SAID, _HEADPHONES, "no quote and no reason word: still asked"),
    ],
)
def test_a_quote_that_does_not_describe_that_problem_is_refused(reason: str, quote: str | None, said: str, items: str, why: str) -> None:
    result = _check(reason, quote, said, items)
    assert result is not None and result["slot"] == "reason_code", why


# --- What already happened in the conversation is evidence ----------------------------------------------------
def _claims(text: str, **state: Any) -> set[str]:
    return {v.kind for v in check_claims(text, {"messages": [], "tool_calls": [], **state})[0]}  # type: ignore[arg-type]


_CONFIRMED_RETURN = {"confirmed_actions": [{"type": "return_request", "return_code": "RT-ABC123", "status": "awaiting_return"}],
                     "open_tickets": []}
_OPEN_TICKET = {"confirmed_actions": [], "open_tickets": [{"code": "TK-AAA111", "status": "open"}]}


def test_a_return_the_customer_confirmed_on_the_card_backs_the_claim_that_it_exists() -> None:
    text = "Yêu cầu trả hàng RT-ABC123 của bạn đã được tạo, bạn gửi hàng trong 5 ngày nhé."
    assert "FALSE_COMPLETION_CLAIM" in _claims(text)
    assert "FALSE_COMPLETION_CLAIM" not in _claims(text, dynamic_context={"conversation_outcomes": _CONFIRMED_RETURN})


def test_a_ticket_opened_in_an_earlier_turn_backs_the_handoff_reply() -> None:
    text = "Yêu cầu của bạn đã được chuyển đến chuyên viên qua phiếu hỗ trợ TK-AAA111. Chuyên viên sẽ liên hệ lại với bạn."
    state: dict[str, Any] = {"messages": [AIMessage(content=text)], "tool_calls": [], "retrieved_clauses": [], "turn_status": "completed"}
    blocked = verify_output_node(state)  # type: ignore[arg-type]
    assert "VERBAL_PROMISE_WITHOUT_TOOL" in (blocked.get("error") or "")
    allowed = verify_output_node({**state, "dynamic_context": {"conversation_outcomes": _OPEN_TICKET}})  # type: ignore[arg-type]
    assert allowed.get("error") is None


# --- Pointing at a "Xác nhận" button is a claim that a card exists --------------------------------------------
@pytest.mark.parametrize("text", ["Bạn vui lòng bấm nút **Xác nhận** để hoàn tất nhé!", "Bạn chỉ cần nhấn Xác nhận là xong."])
def test_any_instruction_to_press_confirm_needs_a_card(text: str) -> None:
    assert "FALSE_PROPOSAL_CLAIM" in _claims(text)
    assert "FALSE_PROPOSAL_CLAIM" not in _claims(text, pending_action={"id": "a-1"})


# --- Database-backed: escalation is idempotent, outcomes are loaded each turn ------------------------------------
@pytest.fixture
async def db():  # type: ignore[no-untyped-def]
    previous = get_clock()
    set_global_clock(Clock(fixed_now=NOW))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    cid = uuid.uuid4()
    async with factory() as s:
        s.add(CustomerModel(id=cid, email="c@example.com", phone="0900000099", full_name="K"))
        await s.commit()
    yield factory, Principal.customer(cid)
    await engine.dispose()
    set_global_clock(previous)


@pytest.mark.asyncio
async def test_asking_for_a_person_again_reuses_the_open_ticket(db) -> None:  # type: ignore[no-untyped-def]
    factory, principal = db
    conv, other = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        service = TicketService(s)
        first = await service.create_ticket(principal, conv, "customer_request", "Khách muốn gặp nhân viên")
        again = await service.create_ticket(principal, conv, "customer_request", "Khách hỏi lại")
        elsewhere = await service.create_ticket(principal, other, "customer_request", "Cuộc trò chuyện khác")
        await s.commit()
        count = len((await s.execute(select(TicketModel).where(TicketModel.conversation_id == conv))).scalars().all())
    assert again.code == first.code and count == 1
    assert elsewhere.code != first.code


@pytest.mark.asyncio
async def test_a_resolved_ticket_does_not_stop_a_new_escalation(db) -> None:  # type: ignore[no-untyped-def]
    factory, principal = db
    conv = uuid.uuid4()
    async with factory() as s:
        service = TicketService(s)
        first = await service.create_ticket(principal, conv, "customer_request", "Lần một")
        first.status = "resolved"
        await s.flush()
        second = await service.create_ticket(principal, conv, "customer_request", "Lần hai")
    assert second.code != first.code


@pytest.mark.asyncio
async def test_each_turn_loads_what_the_conversation_already_produced(db) -> None:  # type: ignore[no-untyped-def]
    factory, principal = db
    conv = uuid.uuid4()
    async with factory() as s:
        order = OrderModel(id=uuid.uuid4(), code="SL-A00001", customer_id=principal.customer_id, status="delivered",
                           payment_method="ewallet", payment_status="paid", subtotal=300000, total=300000, paid_amount=300000)
        s.add(order)
        s.add(ReturnRequestModel(id=uuid.uuid4(), code="RT-ABC123", order_id=order.id, customer_id=principal.customer_id,
                                 reason_code="defective", resolution="refund", status="pending_review", created_at=NOW))
        s.add(PendingActionModel(id=uuid.uuid4(), conversation_id=conv, customer_id=principal.customer_id, type="return_request",
                                 payload={}, payload_hash="h1", preview={}, status="confirmed", presented_at=NOW,
                                 expires_at=NOW + timedelta(minutes=30), result={"return_code": "RT-ABC123", "status": "pending_review"}))
        s.add(PendingActionModel(id=uuid.uuid4(), conversation_id=uuid.uuid4(), customer_id=principal.customer_id, type="cancel_order",
                                 payload={}, payload_hash="h2", preview={}, status="confirmed", presented_at=NOW,
                                 expires_at=NOW + timedelta(minutes=30), result={"status": "cancelled", "order_code": "SL-OTHER1"}))
        await TicketService(s).create_ticket(principal, conv, "customer_request", "Khách muốn gặp nhân viên")
        await s.commit()
        out = await load_context_node(
            {"principal": principal, "conversation_id": str(conv), "clock": NOW, "messages": []},  # type: ignore[typeddict-item]
            {"configurable": {"session": s}},
        )
    outcomes = out["dynamic_context"]["conversation_outcomes"]
    assert outcomes["confirmed_actions"] == [{"type": "return_request", "return_code": "RT-ABC123", "status": "pending_review"}]
    assert [t["status"] for t in outcomes["open_tickets"]] == ["open"]


# --- A refusal is explained from the policy, so the answer has a clause to cite ---------------------------------
from shopagent.agent.tool_requirements import refusal_requirements, unmet_requirements  # noqa: E402

_TOOLS = {"search_policy", "get_order", "propose_cancel_order", "check_return_eligibility"}
_NOT_CANCELLABLE = {"tool": "propose_cancel_order", "args": {"order_code": "SL-A00001"},
                    "result": {"error_code": "ORDER_NOT_CANCELLABLE", "message": "Đơn đang giao."}}
_SEARCHED = {"tool": "search_policy", "args": {"query": "hủy đơn"}, "result": {"status": "success", "results": [{"clause_id": "POL-CANCEL-01"}]}}
_INELIGIBLE = {"tool": "check_return_eligibility", "args": {},
               "result": {"eligible": False, "decision_code": "EXPIRED_WINDOW", "clause_id": "POL-RETURN-02"}}


def test_a_business_refusal_requires_the_policy_behind_it() -> None:
    required = refusal_requirements([_NOT_CANCELLABLE], _TOOLS)
    assert [r.preferred_tool for r in unmet_requirements(required, [_NOT_CANCELLABLE])] == ["search_policy"]
    assert unmet_requirements(required, [_NOT_CANCELLABLE, _SEARCHED]) == []


def test_an_eligibility_refusal_already_carries_its_clause() -> None:
    assert unmet_requirements(refusal_requirements([_INELIGIBLE], _TOOLS), [_INELIGIBLE]) == []


def test_a_missing_slot_is_not_a_refusal_to_explain() -> None:
    missing = {"tool": "propose_cancel_order", "args": {}, "result": {"error_code": "MISSING_SLOT", "slot": "order_code"}}
    assert refusal_requirements([missing], _TOOLS) == []
