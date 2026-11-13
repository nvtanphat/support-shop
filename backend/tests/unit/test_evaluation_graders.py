"""Unit tests for evaluation grading rigor (Issue 1).

Verifies:
1. grade_required_facts supports kind: pattern.
2. grade_required_facts catches and flags unsupported assertion kinds.
3. grade_tool_execution checks tool selection, tool arguments, and execution order constraints.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from evals.harness.graders import (
    grade_db_state,
    grade_forbidden_patterns,
    grade_required_facts,
    grade_tool_execution,
)
from evals.harness.models import ForbiddenPattern, RequiredFact
from evals.harness.runner import load_scenario_from_yaml


def test_grade_required_facts_pattern_success() -> None:
    assistant_texts = ["Dạ em xin phép chuyển cho chuyên viên tư vấn hỗ trợ mình ngay ạ."]
    facts = [RequiredFact(kind="pattern", value="chuyên viên")]
    passed, errors = grade_required_facts(assistant_texts, facts)
    assert passed is True
    assert errors == []


def test_grade_required_facts_pattern_failure() -> None:
    assistant_texts = ["Dạ em sẽ hỗ trợ bạn ngay."]
    facts = [RequiredFact(kind="pattern", value="chuyên viên")]
    passed, errors = grade_required_facts(assistant_texts, facts)
    assert passed is False
    assert any("chuyên viên" in err for err in errors)


def test_grade_required_facts_unsupported_kind_raises_error() -> None:
    assistant_texts = ["Xin chào quý khách."]
    facts = [RequiredFact(kind="unknown_kind", value="some_val")]
    passed, errors = grade_required_facts(assistant_texts, facts)
    assert passed is False
    assert any("UNSUPPORTED_ASSERTION_KIND" in err for err in errors)


def test_grade_tool_execution_selection_and_order() -> None:
    tool_calls = [
        {"tool": "get_order", "args": {"order_code": "SL-100001"}, "result": {"status": "delivered"}},
        {"tool": "check_return_eligibility", "args": {"order_code": "SL-100001", "item_ids": ["it1"], "reason_code": "defective"}, "result": {"eligible": True}},
        {"tool": "propose_return", "args": {"order_code": "SL-100001", "items": [{"item_id": "it1", "qty": 1}], "reason_code": "defective"}, "result": {"action_id": "a1"}},
    ]
    # Ordering: check_return_eligibility must be called before propose_return
    passed, errors = grade_tool_execution(
        tool_calls=tool_calls,
        required_tools=["get_order", "check_return_eligibility", "propose_return"],
        required_args={"get_order": {"order_code": "SL-100001"}},
        ordering_constraints=[("check_return_eligibility", "propose_return")],
    )
    assert passed is True
    assert errors == []


def test_grade_tool_execution_order_violation() -> None:
    # Propose return called BEFORE check_return_eligibility
    tool_calls = [
        {"tool": "propose_return", "args": {"order_code": "SL-100001", "items": [{"item_id": "it1", "qty": 1}], "reason_code": "defective"}},
        {"tool": "check_return_eligibility", "args": {"order_code": "SL-100001", "item_ids": ["it1"], "reason_code": "defective"}},
    ]
    passed, errors = grade_tool_execution(
        tool_calls=tool_calls,
        ordering_constraints=[("check_return_eligibility", "propose_return")],
    )
    assert passed is False
    assert any("ORDERING_VIOLATION" in err for err in errors)


def test_grade_tool_execution_missing_required_tool() -> None:
    tool_calls = [
        {"tool": "get_order", "args": {"order_code": "SL-100001"}},
    ]
    passed, errors = grade_tool_execution(
        tool_calls=tool_calls,
        required_tools=["escalate_to_human"],
    )
    assert passed is False
    assert any("MISSING_TOOL" in err for err in errors)


# ---------------------------------------------------------------------------
# Assertion integrity: every assertion is executed, unknown ones fail loudly
# ---------------------------------------------------------------------------
SCENARIO_DIR = Path(__file__).resolve().parents[3] / "evals" / "scenarios"


def test_asks_for_requires_a_question_about_the_slot() -> None:
    fact = [RequiredFact(kind="asks_for", value="order_code")]
    assert grade_required_facts(["Quý khách cho em xin mã đơn hàng ạ?"], fact)[0] is True
    # Mentioning the words without asking does not count.
    assert grade_required_facts(["Mã đơn hàng của quý khách đã được ghi nhận."], fact)[0] is False
    assert grade_required_facts(["Dạ em đã tạo yêu cầu trả hàng."], fact)[0] is False


def test_asks_for_unknown_slot_is_an_error() -> None:
    passed, errors = grade_required_facts(["Bạn ơi?"], [RequiredFact(kind="asks_for", value="shoe_size")])
    assert passed is False and "UNSUPPORTED_ASSERTION_KIND" in errors[0]


def test_unknown_forbidden_kind_is_an_error_not_a_silent_pass() -> None:
    passed, errors = grade_forbidden_patterns(["x"], [], [ForbiddenPattern(kind="regexp", pattern="x")])
    assert passed is False and "UNSUPPORTED_ASSERTION_KIND" in errors[0]


def test_required_tool_args_fail_when_tool_never_called() -> None:
    passed, errors = grade_tool_execution(
        tool_calls=[], required_args={"propose_return": {"order_code": "SL-1"}}
    )
    assert passed is False and "MISSING_TOOL" in errors[0]


def test_required_tool_args_compare_order_codes_case_insensitively() -> None:
    calls = [{"tool": "get_order", "args": {"order_code": "sl-100001"}}]
    assert grade_tool_execution(calls, required_args={"get_order": {"order_code": "SL-100001"}})[0] is True
    assert grade_tool_execution(calls, required_args={"get_order": {"order_code": "SL-999999"}})[0] is False


def test_unknown_db_table_is_an_error() -> None:
    passed, errors = asyncio.run(grade_db_state(None, {"shipments": [{"status": "x"}]}))  # type: ignore[arg-type]
    assert passed is False and "UNSUPPORTED_ASSERTION_KIND" in errors[0]


def test_loader_rejects_unsupported_assertions(tmp_path: Path) -> None:
    bad = tmp_path / "BAD-001.yaml"
    bad.write_text(
        "id: BAD-001\ngroup: x\nuser:\n  goal: g\n  script:\n  - say: hi\n"
        "expect:\n  required_facts:\n  - kind: sentiment\n    value: nice\n  tool_calls_exactly: 3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported assertions"):
        load_scenario_from_yaml(bad)


def test_every_shipped_scenario_uses_only_supported_assertions() -> None:
    files = sorted(SCENARIO_DIR.glob("*.yaml"))
    assert len(files) >= 38
    for f in files:
        load_scenario_from_yaml(f)  # raises on any unsupported assertion


def test_slot_and_multi_turn_scenarios_exist_with_independent_ground_truth() -> None:
    ids = {load_scenario_from_yaml(f).id for f in SCENARIO_DIR.glob("*.yaml")}
    assert {"SLOT-ORDER-001", "SLOT-ORDER-002", "SLOT-ITEM-001", "SLOT-REASON-001", "MT-RETURN-001", "MT-RETURN-002"} <= ids


def test_polite_request_without_question_mark_counts_as_a_clarification() -> None:
    fact = [RequiredFact(kind="asks_for", value="order_code")]
    polite = "Để hỗ trợ trả hàng, bạn vui lòng cho mình biết **mã đơn hàng** bạn muốn trả (ví dụ SL-710001)."
    assert grade_required_facts([polite], fact)[0] is True
    assert grade_required_facts(["Quý khách vui lòng cung cấp mã đơn hàng ạ."], fact)[0] is True
    # Still a failure: names the slot without asking for it, or asks for something else.
    assert grade_required_facts(["Mã đơn hàng của quý khách đã được ghi nhận."], fact)[0] is False
    assert grade_required_facts(["Bạn vui lòng cho mình biết lý do trả hàng?"], fact)[0] is False


def test_forbidden_claim_ignores_sentences_that_disclaim_it_but_still_catches_real_claims() -> None:
    forbidden = [ForbiddenPattern(kind="claim", pattern="đang tuyển")]
    denial = "Rất tiếc, hệ thống không có thông tin về việc cửa hàng có đang tuyển dụng nhân viên hay không."
    assert grade_forbidden_patterns([denial], [], forbidden)[0] is True
    assert grade_forbidden_patterns(["Dạ shop đang tuyển nhân viên bán hàng ạ."], [], forbidden)[0] is False
    # A disclaimer in another sentence does not excuse a claim made in this one.
    mixed = "Mình không có thông tin về giá. Cửa hàng đang tuyển nhân viên."
    assert grade_forbidden_patterns([mixed], [], forbidden)[0] is False
    # kind: pattern stays a plain substring ban.
    assert grade_forbidden_patterns(["không rõ nhưng thành công"], [], [ForbiddenPattern(kind="pattern", pattern="thành công")])[0] is False
