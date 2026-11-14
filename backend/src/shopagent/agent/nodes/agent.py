"""Node 3: agent - tool-calling loop with tool-first enforcement and a deterministic end state."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.context_window import estimate_text_tokens, prune_messages_token_aware
from shopagent.agent.grounding import check_claims
from shopagent.agent.prompt import render_system_prompt
from shopagent.agent.proposal_guard import find_proposal_conflict
from shopagent.agent.recovery import with_recovery
from shopagent.agent.slot_guard import (
    GroundingContext,
    find_ungrounded_slot,
    recent_order_codes,
    serialize_result,
    stuck_refusal,
    stuck_slot,
    unasked_missing_slots,
)
from shopagent.agent.state import AgentState
from shopagent.agent.tool_requirements import (
    ToolRequirement,
    classify_result,
    derive_requirements,
    draft_steering_message,
    refusal_requirements,
    steering_message,
    unmet_requirements,
    unretrieved_citations,
)
from shopagent.agent.tools.registry import ToolRegistry
from shopagent.core.config import get_models_config
from shopagent.core.principal import Principal
from shopagent.core.text import extract_text_content
from shopagent.infra.llm.factory import get_chat_model

logger = logging.getLogger(__name__)

_MAX_DUPLICATE_CALLS = 2
# Calls of one tool in a single turn. Seen live: nine search_policy calls in a row while the model circled a refusal.
_MAX_CALLS_PER_TOOL = {"search_policy": 3}
_DEFAULT_MAX_CALLS_PER_TOOL = 5
_MAX_STEERING_ROUNDS = 2


@dataclass(frozen=True)
class LoopBudget:
    """Limits of one agent turn, read from config/models.yaml (budgets)."""

    max_iterations: int
    max_input_tokens: int
    turn_timeout_s: float
    tool_timeout_s: float
    synthesis_timeout_s: float
    llm_retry_delays_s: tuple[float, ...]

    @classmethod
    def from_config(cls) -> LoopBudget:
        cfg = get_models_config().get("budgets", {})
        return cls(
            max_iterations=int(cfg.get("max_agent_iterations", 6)),
            max_input_tokens=int(cfg.get("max_input_tokens_per_turn", 12000)),
            turn_timeout_s=float(cfg.get("turn_timeout_s", 90)),
            tool_timeout_s=float(cfg.get("tool_timeout_s", 12)),
            synthesis_timeout_s=float(cfg.get("synthesis_timeout_s", 20)),
            llm_retry_delays_s=tuple(float(d) for d in cfg.get("llm_retry_delays_s", [1.0, 3.0])),
        )


def _latest_user_text(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return extract_text_content(msg.content)
    return ""


def _normalize_ai_message(raw: Any) -> AIMessage:
    """Coerce provider output into an AIMessage with plain-text content and an id."""
    if isinstance(raw, AIMessage):
        msg = raw
        if not isinstance(msg.content, str):
            msg.content = extract_text_content(msg.content)
    else:
        msg = AIMessage(content=extract_text_content(getattr(raw, "content", "")))
    if not msg.id:
        msg.id = f"ai-{uuid.uuid4()}"
    return msg


def _bind_tools(llm: Any, tools: list[Any]) -> Any:
    """Bind tools; models without tool support (the deterministic test model) run tool-less."""
    if not tools:
        return llm
    try:
        return llm.bind_tools(tools)
    except NotImplementedError:
        return llm


_TRANSIENT_MARKERS = (
    "503", "unavailable", "504", "deadline", "timeout", "timed out", "429", "resource_exhausted", "overloaded",
    "connection", "temporarily",
)


def _is_transient(exc: Exception) -> bool:
    """Overload, timeout and quota errors may succeed on retry; a malformed request never will."""
    return any(marker in str(exc).lower() for marker in _TRANSIENT_MARKERS)


_RETRY_HINT_RE = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)\s*s", re.IGNORECASE)
_MAX_RATE_LIMIT_WAIT_S = 20.0


def _retry_wait_s(exc: Exception, default_s: float) -> float:
    """Wait at least as long as the provider asks ("Please retry in 23s"), within a bound."""
    hint = _RETRY_HINT_RE.search(str(exc))
    if hint is None:
        return default_s
    return min(max(default_s, float(hint.group(1)) + 1.0), _MAX_RATE_LIMIT_WAIT_S)


async def _invoke_llm(
    primary: Any,
    fallback_tools: list[Any],
    call_input: list[BaseMessage],
    retry_delays_s: tuple[float, ...],
    deadline: float | None = None,
) -> AIMessage | None:
    """Call the primary model, retrying transient failures with backoff, then the fallback model.

    Every call and every wait is bounded by `deadline` (a time.monotonic() value), so retries and the
    fallback cannot carry the turn far past its timeout. None means no model could answer in time; the
    caller ends the turn as degraded.
    """

    def remaining() -> float | None:
        return None if deadline is None else deadline - time.monotonic()

    async def bounded(coro: Any) -> Any:
        left = remaining()
        if left is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=max(left, 0.001))

    for attempt in range(len(retry_delays_s) + 1):
        left = remaining()
        if left is not None and left <= 0:
            logger.error("llm_turn_deadline_reached attempt=%d", attempt + 1)
            return None
        try:
            return _normalize_ai_message(await bounded(primary.ainvoke(call_input)))
        except Exception as exc:
            transient = isinstance(exc, TimeoutError) or _is_transient(exc)
            logger.warning("llm_call_failed attempt=%d transient=%s error=%r", attempt + 1, transient, exc)
            if not transient or attempt == len(retry_delays_s):
                break
            wait = _retry_wait_s(exc, retry_delays_s[attempt])
            left = remaining()
            if left is not None and wait >= left:
                break  # no time for another attempt; try the fallback with what is left
            await asyncio.sleep(wait)
    left = remaining()
    if left is not None and left <= 0:
        return None
    try:
        fallback = _bind_tools(get_chat_model("agent_fallback"), fallback_tools)
        return _normalize_ai_message(await bounded(fallback.ainvoke(call_input)))
    except Exception as exc:
        logger.error("llm_fallback_failed error=%r", exc)
        return None


async def _run_tool_call(
    call: ToolCall,
    tools_by_name: dict[str, Any],
    sig_counts: dict[str, int],
    tool_timeout_s: float,
    grounding: GroundingContext,
) -> Any:
    """Execute one tool call with duplicate protection and a timeout."""
    name = call["name"]
    args = call.get("args", {})
    tool = tools_by_name.get(name)
    if tool is None:
        return {
            "error_code": "TOOL_NOT_FOUND",
            "message": f"Công cụ '{name}' không tồn tại hoặc không được phép dùng cho vai trò này.",
        }

    missing_slot = find_ungrounded_slot(name, args, grounding)
    if missing_slot is not None:
        logger.info("tool_rejected_ungrounded tool=%s reason=%s", name, missing_slot.get("slot") or missing_slot["error_code"])
        return missing_slot

    tool_calls_made = sig_counts.get(f"#{name}", 0) + 1
    sig_counts[f"#{name}"] = tool_calls_made
    if tool_calls_made > _MAX_CALLS_PER_TOOL.get(name, _DEFAULT_MAX_CALLS_PER_TOOL):
        return with_recovery({"error_code": "TOOL_CALL_LIMIT", "message": f"Công cụ '{name}' đã được gọi quá nhiều lần trong lượt này."})
    signature = f"{name}:{json.dumps(args, sort_keys=True, default=str)}"
    sig_counts[signature] = sig_counts.get(signature, 0) + 1
    if sig_counts[signature] > _MAX_DUPLICATE_CALLS:
        return {
            "error_code": "DUPLICATE_CALL",
            "message": f"Công cụ '{name}' đã được gọi nhiều lần với cùng tham số. "
            "Hãy dùng kết quả đã có hoặc hỏi thêm khách.",
        }
    try:
        return with_recovery(await asyncio.wait_for(tool.ainvoke(args), timeout=tool_timeout_s))
    except TimeoutError:
        logger.error("tool_timeout tool=%s timeout_s=%s", name, tool_timeout_s)
        return {"error_code": "TOOL_TIMEOUT", "message": f"Công cụ '{name}' phản hồi quá lâu."}
    except Exception as exc:
        logger.warning("tool_failed tool=%s error=%s", name, exc)
        return {"error_code": "TOOL_EXECUTION_ERROR", "message": str(exc)}


async def _synthesize_final(
    llm: Any, sys_msg: SystemMessage, working: list[BaseMessage], timeout_s: float
) -> AIMessage | None:
    """Ask the tool-less model for a final answer from the tool results already gathered."""
    instruction = HumanMessage(
        content=(
            "[HỆ THỐNG - không phải lời khách] Hãy trả lời khách đầy đủ, rõ ràng, lịch sự chỉ dựa trên "
            "kết quả công cụ đã có. Không gọi thêm công cụ. Nếu thiếu dữ liệu, nói rõ phần còn thiếu."
        )
    )
    try:
        resp = await asyncio.wait_for(
            llm.ainvoke([sys_msg, *working, instruction]), timeout=timeout_s
        )
    except Exception as exc:
        logger.warning("synthesis_failed error=%s", exc)
        return None
    final = _normalize_ai_message(resp)
    final.tool_calls = []
    return final if extract_text_content(final.content).strip() else None


def _refusal_requirements(recorded: list[dict[str, Any]], tools_by_name: dict[str, Any], tools_off: bool) -> list[ToolRequirement]:
    """The clause behind a refusal, unless the tools are already off: then the model cannot fetch it, and an
    explanation without a citation serves the customer better than the turn failing on an unmeetable requirement."""
    return [] if tools_off else refusal_requirements(recorded, tools_by_name)


async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Run the bounded tool loop and report how the turn ended in `turn_status`."""
    session = config.get("configurable", {}).get("session")
    if not session or not isinstance(session, AsyncSession):
        raise ValueError("AsyncSession must be provided in config['configurable']['session']")

    budget = LoopBudget.from_config()
    started = time.monotonic()
    principal = state.get("principal") or Principal.guest()
    conv_id_str = state.get("conversation_id")
    conv_id = uuid.UUID(conv_id_str) if conv_id_str else uuid.uuid4()

    retrieved_clauses: list[str] = list(state.get("retrieved_clauses", []))
    proposed_actions: list[dict[str, Any]] = []
    tools = ToolRegistry(session).get_tools(
        principal=principal,
        conversation_id=conv_id,
        retrieved_clauses=retrieved_clauses,
        proposed_actions_out=proposed_actions,
    )
    tools_by_name = {t.name: t for t in tools}

    llm = get_chat_model("agent_primary")
    llm_with_tools = _bind_tools(llm, tools)
    sys_msg = SystemMessage(content=render_system_prompt(state))
    history = list(state.get("messages", []))
    # System prompt and tool schemas are sent on every call, so they count against the input budget.
    reserved = estimate_text_tokens(sys_msg.content if isinstance(sys_msg.content, str) else "") + sum(
        estimate_text_tokens(json.dumps(t.get_input_jsonschema())) for t in tools
    )
    working = prune_messages_token_aware(history, max_input_tokens=budget.max_input_tokens, reserved_tokens=reserved)

    dynamic_context = state.get("dynamic_context") or {}
    requirements = derive_requirements(_latest_user_text(history), tools_by_name)
    new_messages: list[BaseMessage] = []
    recorded: list[dict[str, Any]] = []
    sig_counts: dict[str, int] = {}
    steering_rounds = 0
    tools_off = False  # set once a slot is stuck: the rest of the turn is spent asking the customer
    llm_seconds = tool_seconds = 0.0
    llm_calls = 0
    turn_status = "incomplete"
    unmet: list[ToolRequirement] = []

    for iteration in range(budget.max_iterations):
        if time.monotonic() - started > budget.turn_timeout_s:
            logger.error("turn_timeout elapsed_s=%.1f", time.monotonic() - started)
            break

        # The final iterations are reserved for the answer: tools off, so the model cannot spend the budget on
        # lookups and leave only a last draft that can no longer be corrected.
        if not tools_off and iteration >= budget.max_iterations - budget.max_iterations // 4 and recorded:
            tools_off = True
            working.append(
                HumanMessage(
                    content="[HỆ THỐNG - không phải lời khách]\n"
                    "Đã hết lượt tra cứu. Không gọi thêm công cụ: hãy trả lời khách ngay từ kết quả đã có (hoặc hỏi thêm khách "
                    "nếu còn thiếu thông tin). Chỉ nêu điều có trong kết quả công cụ."
                )
            )
        stuck = stuck_slot(recorded)
        refused = stuck_refusal(recorded)
        if (stuck is not None or refused is not None) and not tools_off:
            tools_off = True
            if stuck is not None:
                instruction = (
                    f"Công cụ đã báo thiếu '{stuck}' nhiều lần và không thể tự có thông tin này. Không gọi thêm công cụ nào: "
                    "hãy hỏi khách đúng thông tin còn thiếu trong một câu ngắn (lý do trả hàng thì hỏi câu đóng nêu lý do "
                    "gần với lời khách, như 'Sản phẩm bị lỗi phải không ạ?' hoặc 'Bạn đổi ý không dùng nữa phải không ạ?'; "
                    "nhiều đơn thì liệt kê và hỏi khách chọn đơn nào)."
                )
            else:
                instruction = (
                    f"Công cụ đã từ chối nhiều lần với cùng lý do ({refused}); thử lại không đổi được kết quả. Không gọi thêm "
                    "công cụ nào: hãy nói rõ cho khách vì sao chưa làm được, theo `next_step` trong kết quả công cụ, và đưa "
                    "ra hướng thay thế để khách chọn (một câu hỏi ngắn). Không hỏi khách thứ không làm thay đổi kết quả."
                )
            working.append(HumanMessage(content="[HỆ THỐNG - không phải lời khách]\n" + instruction))
        llm_started = time.monotonic()
        ai = await _invoke_llm(
            llm if tools_off else llm_with_tools,
            [] if tools_off else tools,
            [sys_msg, *working],
            budget.llm_retry_delays_s,
            deadline=started + budget.turn_timeout_s,
        )
        llm_seconds += time.monotonic() - llm_started
        llm_calls += 1
        if ai is None:
            turn_status = "degraded"
            break
        working.append(ai)

        if not ai.tool_calls:
            unmet = unmet_requirements([*requirements, *_refusal_requirements(recorded, tools_by_name, tools_off)], recorded)
            draft = extract_text_content(ai.content)
            unretrieved = unretrieved_citations(draft, retrieved_clauses)
            draft_state: dict[str, Any] = {
                "messages": [*history, *new_messages],
                "tool_calls": recorded,
                "dynamic_context": dynamic_context,
            }
            claim_problems = [f"{v.kind}: {v.claim} ({v.detail})" for v in check_claims(draft, draft_state)[0]]  # type: ignore[arg-type]
            claim_problems += unasked_missing_slots(recorded, draft)
            is_last = iteration == budget.max_iterations - 1
            if not unmet and (unretrieved or claim_problems) and steering_rounds < _MAX_STEERING_ROUNDS and not is_last:
                # verify_output would replace this draft with a refusal; ask the model to fix it while it still can.
                steering_rounds += 1
                working.append(
                    HumanMessage(content="[HỆ THỐNG - không phải lời khách]" + chr(10) + draft_steering_message(unretrieved, claim_problems))
                )
                continue
            if not unmet:
                new_messages.append(ai)
                turn_status = "completed"
                break
            if steering_rounds >= _MAX_STEERING_ROUNDS or is_last:
                turn_status = "requirements_unmet"
                break
            # The non-compliant answer stays out of persisted history.
            steering_rounds += 1
            working.append(HumanMessage(content=f"[HỆ THỐNG - không phải lời khách]\n{steering_message(unmet)}"))
            continue

        new_messages.append(ai)
        for call in ai.tool_calls:
            grounding = GroundingContext([*history, *new_messages], recent_order_codes(dynamic_context))
            tool_started = time.monotonic()
            result = find_proposal_conflict(
                call["name"], recorded, dynamic_context.get("active_pending_action")
            ) or await _run_tool_call(call, tools_by_name, sig_counts, budget.tool_timeout_s, grounding)
            tool_ms = (time.monotonic() - tool_started) * 1000
            tool_seconds += tool_ms / 1000
            logger.info("tool_done tool=%s outcome=%s ms=%d", call.get("name"), classify_result(result).value, tool_ms)
            recorded.append(
                {
                    "tool": call.get("name"),
                    "args": call.get("args", {}),
                    "result": result,
                    "outcome": classify_result(result).value,
                }
            )
            tool_msg = ToolMessage(
                content=serialize_result(result),
                name=call.get("name"),
                tool_call_id=call.get("id") or str(uuid.uuid4()),
            )
            working.append(tool_msg)
            new_messages.append(tool_msg)

    if turn_status == "incomplete" and recorded:
        final = await _synthesize_final(llm, sys_msg, working, budget.synthesis_timeout_s)
        if final is not None:
            unmet = unmet_requirements([*requirements, *_refusal_requirements(recorded, tools_by_name, tools_off)], recorded)
            if unmet:
                turn_status = "requirements_unmet"
            else:
                new_messages.append(final)
                turn_status = "synthesized"
    if turn_status == "incomplete":
        turn_status = "degraded"

    logger.info(
        "agent_turn_done conv_id=%s status=%s tools=%d unmet=%d duration_s=%.2f llm_s=%.2f llm_calls=%d tool_s=%.2f",
        conv_id_str, turn_status, len(recorded), len(unmet), time.monotonic() - started, llm_seconds, llm_calls, tool_seconds,
    )

    update: dict[str, Any] = {
        "messages": new_messages,
        "retrieved_clauses": sorted(set(retrieved_clauses)),
        "tool_calls": recorded,
        "turn_status": turn_status,
        "unmet_requirements": [r.key for r in unmet] if turn_status == "requirements_unmet" else [],
    }
    if proposed_actions:
        update["pending_action"] = proposed_actions[-1]
    return update
