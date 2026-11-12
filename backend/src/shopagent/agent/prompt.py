"""System prompt rendering from verified per-turn context."""

from __future__ import annotations

import jinja2

from shopagent.agent.state import AgentState
from shopagent.core.clock import get_clock
from shopagent.core.config import CONFIG_DIR, get_rules_config

_PROCEDURES_DIR = CONFIG_DIR / "procedures"

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(CONFIG_DIR / "prompts")),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


def _load_procedures() -> str:
    """Load and concatenate all markdown procedures."""
    if not _PROCEDURES_DIR.exists():
        return ""
    return "\n\n".join(f.read_text(encoding="utf-8") for f in sorted(_PROCEDURES_DIR.glob("*.md")))


_ALL_PROCEDURES = _load_procedures()


def render_system_prompt(state: AgentState) -> str:
    """Render the system prompt template with dynamic context."""
    template = _jinja_env.get_template("system.md.j2")
    clock = state.get("clock") or get_clock().now()
    principal = state.get("principal")
    dynamic_context = state.get("dynamic_context") or {}

    role_val = principal.role.value if principal else "guest"

    active_action = dynamic_context.get("active_pending_action")
    recent_orders = dynamic_context.get("recent_orders") or []
    policy_version = dynamic_context.get("policy_version") or str(get_rules_config()["version"])

    return template.render(
        store_name="ShopLab",
        procedures=_ALL_PROCEDURES,
        current_time=clock.strftime("%d/%m/%Y %H:%M:%S UTC"),
        principal_role=role_val,
        active_proposal=active_action,
        active_cases=None,
        recent_orders=recent_orders,
        policy_version=policy_version,
    )
