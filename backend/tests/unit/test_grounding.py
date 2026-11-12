"""Claim-to-evidence verification: only successful tool facts back a claim."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from shopagent.agent.nodes.verify_output import verify_output_node
from shopagent.agent.state import AgentState


def call(tool: str, result: dict, **args: str) -> dict:
    return {"tool": tool, "args": args, "result": result}


def verify(answer: str, tool_calls: list[dict], customer: str = "Cho mình hỏi", **extra) -> dict:  # type: ignore[no-untyped-def]
    state: AgentState = {
        "messages": [HumanMessage(content=customer), AIMessage(content=answer)],
        "tool_calls": tool_calls,
        **extra,
    }
    return verify_output_node(state)


REFUND_DONE = call("get_case_status", {"case_type": "refund", "code": "RF-1", "status": "succeeded", "amount": 440000})
REFUND_PENDING = call("get_case_status", {"case_type": "refund", "code": "RF-1", "status": "pending_approval", "amount": 440000})


def test_refund_completion_claim_needs_a_succeeded_refund_in_tool_results() -> None:
    answer = "Dạ khoản hoàn 440.000 đ đã hoàn tiền về ví của quý khách ạ."
    assert "error" not in verify(answer, [REFUND_DONE])
    for evidence in ([], [REFUND_PENDING]):
        res = verify(answer, evidence)
        assert "FALSE_COMPLETION_CLAIM" in res["error"]


def test_failed_tool_result_is_not_evidence_for_a_number() -> None:
    failed = call("check_return_eligibility", {"error_code": "TOOL_TIMEOUT", "message": "hoàn 440000 đ"})
    res = verify("Dạ quý khách sẽ nhận 440.000 đ ạ.", [failed])
    assert "UNSUPPORTED_NUMBER" in res["error"]


def test_only_the_latest_customer_message_can_echo_a_number() -> None:
    state: AgentState = {
        "messages": [
            HumanMessage(content="Hàng mình nhận 30 ngày rồi"),
            AIMessage(content="Dạ em xin ghi nhận."),
            HumanMessage(content="Còn đơn kia thì sao?"),
            AIMessage(content="Đơn đó đã quá 30 ngày nên không đổi được ạ."),
        ],
    }
    assert "UNSUPPORTED_NUMBER" in verify_output_node(state)["error"]


def test_order_code_must_come_from_a_lookup_or_the_customer() -> None:
    owned = call("get_order", {"order_code": "SL-111111", "status": "delivered", "total": 250000})
    assert "error" not in verify("Đơn SL-111111 đã giao, tổng 250.000 đ ạ.", [owned], customer="Đơn SL-111111 sao rồi")
    res = verify("Đơn SL-999999 đã giao ạ.", [owned], customer="Đơn SL-111111 sao rồi")
    assert "UNSUPPORTED_ORDER" in res["error"]


def test_cancel_completion_needs_order_status_cancelled() -> None:
    cancelled = call("get_order", {"order_code": "SL-1", "status": "cancelled"})
    still_open = call("get_order", {"order_code": "SL-1", "status": "confirmed"})
    answer = "Dạ đơn SL-1 đã hủy đơn thành công ạ."
    assert "error" not in verify(answer, [cancelled], customer="hủy đơn SL-1")
    assert "FALSE_COMPLETION_CLAIM" in verify(answer, [still_open], customer="hủy đơn SL-1")["error"]


def test_supported_claims_are_traced_to_their_source_tool() -> None:
    eligibility = call("check_return_eligibility", {"eligible": True, "estimated_refund": 440000, "clause_id": "POL-RETURN-02"})
    res = verify("Dạ khoản hoàn ước tính là 440.000 đ ạ.", [eligibility])
    assert res["claim_evidence"] == {"440.000 đ": "check_return_eligibility"}
