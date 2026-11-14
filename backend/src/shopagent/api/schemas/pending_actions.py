"""One wire format for a proposed action, whichever endpoint or event delivers it.

The agent tools, the conversation detail and the SSE stream each used to describe the same proposal with
different field names (`action_id` or `id`, `preview_hash` or `payload_hash`), and the UI reads one set.
"""

from __future__ import annotations

from typing import Any

from shopagent.agent.presentation import CODE_LABELS


def _preview_for_ui(preview: dict[str, Any]) -> dict[str, Any]:
    shaped = dict(preview)
    shaped.setdefault("description", preview.get("message") or "")
    refund = preview.get("estimated_refund", preview.get("refund_amount"))
    if refund is not None:
        shaped.setdefault("estimated_refund_vnd", refund)
    if "needs_approval" in preview:
        shaped.setdefault("requires_approval", preview["needs_approval"])
    # The card is where the customer confirms the reason the assistant chose, so it is shown in plain words.
    reason = preview.get("reason_code")
    if isinstance(reason, str) and reason in CODE_LABELS:
        shaped.setdefault("reason_label", CODE_LABELS[reason])
    return shaped


def pending_action_dto(
    data: dict[str, Any] | None,
    *,
    conversation_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """Normalise a proposal dict from a tool result, a stored event or a database row."""
    if not data:
        return None
    action_id = str(data.get("id") or data.get("action_id") or "")
    digest = data.get("payload_hash") or data.get("preview_hash") or ""
    return {
        "id": action_id,
        "action_id": action_id,
        "conversation_id": str(data.get("conversation_id") or conversation_id or ""),
        "type": data.get("type", ""),
        "preview": _preview_for_ui(data.get("preview") or {}),
        "payload_hash": digest,
        "preview_hash": digest,
        "status": status or data.get("status") or "proposed",
        "presented_at": data.get("presented_at"),
        "expires_at": data.get("expires_at"),
    }
