"""Grade which tools an agent called, with which arguments and in which order."""

from __future__ import annotations

from typing import Any

from shopagent.agent.tool_requirements import ToolOutcome, classify_result


def _arg_equals(actual: Any, expected: Any) -> bool:
    """Compare tool arguments; order codes are case-insensitive identifiers."""
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip().upper() == expected.strip().upper()
    return bool(actual == expected)


def _call_succeeded(call: dict[str, Any]) -> bool:
    """A call counts as executed unless its result is a failure; a record without a result never does."""
    if "result" not in call:
        return False
    return classify_result(call["result"]) is not ToolOutcome.FAILED


def score_tool_use(
    tool_calls: list[dict[str, Any]],
    required_tools: list[str] | None = None,
    required_args: dict[str, dict[str, Any]] | None = None,
    ordering_constraints: list[tuple[str, str]] | None = None,
) -> dict[str, int]:
    """Counts behind the tool-use metrics (selection, arguments, execution success, order)."""
    names = [tc.get("tool") or tc.get("name", "") for tc in tool_calls]
    score = dict.fromkeys(
        ("required_total", "required_called", "required_succeeded", "args_total", "args_matched", "order_total", "order_ok"), 0
    )
    for tool in required_tools or []:
        score["required_total"] += 1
        calls = [tc for tc in tool_calls if (tc.get("tool") or tc.get("name")) == tool]
        score["required_called"] += bool(calls)
        score["required_succeeded"] += any(_call_succeeded(tc) for tc in calls)
    for tool, expected in (required_args or {}).items():
        score["args_total"] += 1
        calls = [tc for tc in tool_calls if (tc.get("tool") or tc.get("name")) == tool]
        score["args_matched"] += any(
            all(_arg_equals((tc.get("args") or {}).get(k), v) for k, v in expected.items()) for tc in calls
        )
    for first, second in ordering_constraints or []:
        score["order_total"] += 1
        if first in names and second in names:
            score["order_ok"] += names.index(first) < names.index(second)
    return score


def grade_tool_execution(
    tool_calls: list[dict[str, Any]],
    required_tools: list[str] | None = None,
    required_args: dict[str, dict[str, Any]] | None = None,
    ordering_constraints: list[tuple[str, str]] | None = None,
) -> tuple[bool, list[str]]:
    """Verify tool selection, arguments, and execution ordering constraints."""
    errors: list[str] = []
    executed_tools: list[str] = [tc.get("tool") or tc.get("name", "") for tc in tool_calls]

    # 1. Required tools selection
    if required_tools:
        for req in required_tools:
            if req not in executed_tools:
                errors.append(f"MISSING_TOOL: Required tool '{req}' was not invoked. Invoked: {executed_tools}")

    # 1b. A required tool that was only ever called and failed is not a completed step
    for req in required_tools or []:
        calls = [tc for tc in tool_calls if (tc.get("tool") or tc.get("name")) == req]
        if calls and not any(_call_succeeded(tc) for tc in calls):
            errors.append(f"TOOL_NOT_SUCCEEDED: Required tool '{req}' was called but never succeeded")

    # 2. Required tool arguments
    if required_args:
        for tool_name, exp_args in required_args.items():
            matching_calls = [tc for tc in tool_calls if (tc.get("tool") or tc.get("name")) == tool_name]
            if not matching_calls:
                errors.append(f"MISSING_TOOL: Tool '{tool_name}' with expected arguments {exp_args} was never invoked")
                continue
            matched = False
            for mc in matching_calls:
                call_args = mc.get("args") or {}
                if all(_arg_equals(call_args.get(k), v) for k, v in exp_args.items()):
                    matched = True
                    break
            if not matched:
                errors.append(
                    f"ARGUMENT_MISMATCH: Tool '{tool_name}' invoked without expected arguments {exp_args}. "
                    f"Actual calls: {[mc.get('args') for mc in matching_calls]}"
                )

    # 3. Ordering constraints: (first_tool, second_tool)
    if ordering_constraints:
        for first_tool, second_tool in ordering_constraints:
            first_indices = [i for i, name in enumerate(executed_tools) if name == first_tool]
            second_indices = [i for i, name in enumerate(executed_tools) if name == second_tool]

            if second_indices:
                if not first_indices:
                    errors.append(
                        f"ORDERING_VIOLATION: Tool '{second_tool}' was called, but prerequisite '{first_tool}' was never called."
                    )
                elif min(first_indices) > min(second_indices):
                    errors.append(
                        f"ORDERING_VIOLATION: Tool '{first_tool}' (index {min(first_indices)}) must be called before '{second_tool}' (index {min(second_indices)})."
                    )

    return (len(errors) == 0, errors)
