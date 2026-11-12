"""Node 3: agent - Main reasoning loop with tool binding, execution, timeout, and anti-thrashing."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import time
from typing import Any
import uuid
import jinja2
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from shopagent.agent.state import AgentState
from shopagent.agent.tools.registry import ToolRegistry
from shopagent.core.clock import get_clock
from shopagent.core.config import CONFIG_DIR
from shopagent.core.principal import Principal
from shopagent.core.text import extract_text_content
from shopagent.infra.llm.factory import get_chat_model


logger = logging.getLogger(__name__)

_TEMPLATE_DIR = CONFIG_DIR / "prompts"
_PROCEDURES_DIR = CONFIG_DIR / "procedures"

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


def _load_procedures() -> str:
    """Load and concatenate all markdown procedures."""
    if not _PROCEDURES_DIR.exists():
        return ""
    procedures = []
    for f in sorted(_PROCEDURES_DIR.glob("*.md")):
        procedures.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(procedures)


_ALL_PROCEDURES = _load_procedures()


def render_system_prompt(state: AgentState) -> str:
    """Render the system prompt template with dynamic context."""
    template = _jinja_env.get_template("system.md.j2")
    clock = state.get("clock") or get_clock().now()
    principal = state.get("principal")
    dynamic_context = state.get("dynamic_context") or {}

    role_val = principal.role.value if principal else "guest"
    p_id = str(principal.customer_id) if principal and principal.customer_id else "guest"

    active_action = dynamic_context.get("active_pending_action")

    return template.render(
        store_name="ShopLab",
        procedures=_ALL_PROCEDURES,
        current_time=clock.strftime("%d/%m/%Y %H:%M:%S UTC"),
        principal_role=role_val,
        principal_id=p_id,
        active_proposal=active_action,
        active_cases=None,
    )


async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Execute LLM agent loop with bound tools up to max 6 iterations with timeout & loop prevention."""
    session: AsyncSession = config.get("configurable", {}).get("session")
    if not session:
        raise ValueError("AsyncSession must be provided in config['configurable']['session']")

    start_turn = time.perf_counter()
    principal = state.get("principal") or Principal.guest()
    conv_id_str = state.get("conversation_id")
    conv_id = uuid.UUID(conv_id_str) if conv_id_str else uuid.uuid4()

    retrieved_clauses = list(state.get("retrieved_clauses", []))
    proposed_actions: list[dict[str, Any]] = []

    # Get authorized tools for this principal
    registry = ToolRegistry(session)
    tools = registry.get_tools(
        principal=principal,
        conversation_id=conv_id,
        retrieved_clauses=retrieved_clauses,
        proposed_actions_out=proposed_actions,
    )
    tools_by_name = {t.name: t for t in tools}

    # Prepare chat model
    llm = get_chat_model("agent_primary")
    if tools:
        try:
            llm_with_tools = llm.bind_tools(tools)
        except Exception:
            llm_with_tools = llm
    else:
        llm_with_tools = llm

    # System prompt
    sys_prompt = render_system_prompt(state)
    sys_msg = SystemMessage(content=sys_prompt)

    # Conversation history with budget limit (sliding window of last 12 messages)
    history = list(state.get("messages", []))
    if len(history) > 12:
        working_messages: list[BaseMessage] = list(history[-12:])
    else:
        working_messages = list(history)

    new_messages: list[BaseMessage] = []
    recorded_tool_calls: list[dict[str, Any]] = []
    sig_counts: dict[str, int] = {}

    max_iterations = 6
    for iteration in range(max_iterations):
        call_input = [sys_msg, *working_messages]
        ai_response = None

        # Retry transient errors up to 2 times, then switch to agent_fallback
        for attempt in range(3):
            try:
                ai_response = await llm_with_tools.ainvoke(call_input)
                break
            except Exception as e:
                logger.warning("Lỗi gọi LLM lần %d (vòng %d): %s", attempt + 1, iteration + 1, e)
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    try:
                        fallback_llm = get_chat_model("agent_fallback")
                        if tools:
                            try:
                                fallback_with_tools = fallback_llm.bind_tools(tools)
                            except Exception:
                                fallback_with_tools = fallback_llm
                        else:
                            fallback_with_tools = fallback_llm
                        ai_response = await fallback_with_tools.ainvoke(call_input)
                    except Exception as fb_err:
                        logger.error("Gọi fallback LLM cũng thất bại: %s", fb_err)
                        ai_response = AIMessage(
                            content="Dạ hiện tại hệ thống AI đang tạm thời gián đoạn kết nối. Quý khách vui lòng thử lại sau giây lát hoặc bấm nút gặp nhân viên để được hỗ trợ trực tiếp ạ."
                        )

        if not ai_response:
            ai_response = AIMessage(
                content="Dạ em có thể hỗ trợ quý khách thông tin gì thêm về đơn hàng hoặc chính sách cửa hàng ạ?"
            )

        if isinstance(ai_response, AIMessage) and not isinstance(ai_response.content, str):
            ai_response.content = extract_text_content(ai_response.content)

        working_messages.append(ai_response)
        new_messages.append(ai_response)

        # Check if the model called any tools
        tool_calls = getattr(ai_response, "tool_calls", None)
        if not tool_calls:
            # Model responded with final text
            break

        # Execute each tool call
        for call in tool_calls:
            tool_name = call.get("name")
            tool_args = call.get("args", {})
            call_id = call.get("id") or str(uuid.uuid4())

            target_tool = tools_by_name.get(tool_name)
            if not target_tool:
                res_content = {
                    "error_code": "TOOL_NOT_FOUND",
                    "message": f"Công cụ '{tool_name}' không tồn tại hoặc không được phép dùng cho vai trò của bạn.",
                }
            else:
                # Anti-thrashing check
                try:
                    call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                except Exception:
                    call_sig = f"{tool_name}:{str(tool_args)}"

                sig_counts[call_sig] = sig_counts.get(call_sig, 0) + 1
                if sig_counts[call_sig] > 2:
                    res_content = {
                        "error_code": "DUPLICATE_CALL",
                        "message": f"Công cụ '{tool_name}' đã được gọi trước đó với cùng tham số. Vui lòng sử dụng thông tin đã có để giải đáp hoặc hỏi thêm thông tin từ khách hàng.",
                    }
                else:
                    # Execute tool with strict 12-second timeout
                    try:
                        res_content = await asyncio.wait_for(target_tool.ainvoke(tool_args), timeout=12.0)
                    except asyncio.TimeoutError:
                        logger.error("Công cụ '%s' hết thời gian chờ (12s)", tool_name)
                        res_content = {
                            "error_code": "TOOL_TIMEOUT",
                            "message": f"Công cụ '{tool_name}' phản hồi quá lâu (hơn 12s).",
                        }
                    except Exception as e:
                        logger.warning("Lỗi thực thi công cụ '%s': %s", tool_name, e)
                        res_content = {"error_code": "TOOL_EXECUTION_ERROR", "message": str(e)}

            recorded_tool_calls.append({
                "tool": tool_name,
                "args": tool_args,
                "result": res_content,
            })

            tool_msg = ToolMessage(
                content=json.dumps(res_content, ensure_ascii=False) if not isinstance(res_content, str) else res_content,
                name=tool_name,
                tool_call_id=call_id,
            )
            working_messages.append(tool_msg)
            new_messages.append(tool_msg)

    elapsed = time.perf_counter() - start_turn
    logger.info(
        "Agent turn completed | conv_id=%s | tools_called=%d | duration=%.2fs",
        conv_id_str,
        len(recorded_tool_calls),
        elapsed,
    )

    update: dict[str, Any] = {
        "messages": new_messages,
        "retrieved_clauses": list(set(retrieved_clauses)),
        "tool_calls": recorded_tool_calls,
    }

    if proposed_actions:
        update["pending_action"] = proposed_actions[-1]

    return update
