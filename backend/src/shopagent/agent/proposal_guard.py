"""Stop duplicate action proposals before a second confirmation card is created.

The customer confirms through an authenticated API, so two live cards for the same operation would
let one request be confirmed twice or leave a stale card on screen. The domain still re-checks at
commit time; this guard only keeps the conversation tidy and the model honest.
"""

from __future__ import annotations

from typing import Any

PROPOSAL_TOOLS = {"propose_return": "return", "propose_cancel_order": "cancel"}


def find_proposal_conflict(
    tool: str,
    executed_this_turn: list[dict[str, Any]],
    active_pending_action: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return an error result when a proposal for this operation already exists, else None."""
    kind = PROPOSAL_TOOLS.get(tool)
    if kind is None:
        return None
    for call in executed_this_turn:
        result = call.get("result") or {}
        if call.get("tool") in PROPOSAL_TOOLS and "action_id" in result and "error_code" not in result:
            return {
                "error_code": "PROPOSAL_ALREADY_CREATED",
                "message": "Lượt này đã tạo một đề xuất. Chỉ tạo tối đa một đề xuất mỗi lượt; hãy báo khách kiểm tra thẻ đề xuất.",
            }
    if active_pending_action and kind in str(active_pending_action.get("type", "")).lower():
        return {
            "error_code": "PENDING_ACTION_EXISTS",
            "message": (
                "Đang có một đề xuất cùng loại chờ khách xác nhận trên màn hình. Hãy nhắc khách xác nhận hoặc "
                "hủy đề xuất đó trước khi tạo đề xuất mới; không tạo thêm."
            ),
            "existing_action_code": active_pending_action.get("code"),
        }
    return None
