"""Deterministic scripted user simulation for evaluation harness."""

from __future__ import annotations

from typing import Any

from evals.harness.models import UserScript


class ScriptedUser:
    """Deterministic customer agent reacting to assistant messages and action proposals."""

    ASKED_KEYWORDS: dict[str, list[str]] = {
        "reason": ["lý do", "nguyên nhân", "tại sao", "vấn đề", "vì sao", "gặp sự cố gì"],
        "condition": ["tình trạng", "còn nguyên", "đã dùng", "tem", "mác", "hộp", "sử dụng chưa"],
        "order_code": ["mã đơn", "số đơn", "đơn hàng nào", "mã của đơn", "tra cứu đơn nào"],
        "items": ["sản phẩm nào", "món nào", "mặt hàng", "cần trả món nào", "chiếc nào"],
        "payout": ["số tài khoản", "ngân hàng", "stk", "thông tin tài khoản", "thụ hưởng"],
        "exchange_variant": ["kích cỡ", "size", "màu", "đổi sang", "phân loại"],
    }

    def __init__(self, script: UserScript) -> None:
        self.script = script
        self.step_index = 0
        self.total_turns = 0
        self.fallback_turns = 0
        self._matched_steps: set[int] = set()

    def respond(
        self,
        assistant_text: str | None,
        pending_action: dict[str, Any] | None = None,
    ) -> tuple[str, str | None, dict[str, Any] | None]:
        """Determine next customer action.

        Returns:
            (reply_text, action_decision: 'confirm' | 'cancel' | None, action_payload: dict | None)
        """
        self.total_turns += 1

        # Turn 1: If assistant has not spoken yet, start with first say step
        if assistant_text is None and self.step_index == 0:
            for idx, step in enumerate(self.script.script):
                if step.say and not step.when_asked and not step.on_proposal:
                    self._matched_steps.add(idx)
                    return step.say, None, None
            return self.script.goal, None, None

        # 1. Check if there is an active proposal that matches on_proposal
        if pending_action:
            for idx, step in enumerate(self.script.script):
                if idx in self._matched_steps:
                    continue
                if step.on_proposal:
                    expected_type = step.on_proposal.get("type")
                    act_type = pending_action.get("type")
                    if expected_type and (expected_type == act_type or expected_type in str(act_type)):
                        self._matched_steps.add(idx)
                        return (
                            step.say or "Mình đồng ý xác nhận.",
                            step.do or "confirm",
                            pending_action,
                        )

        # 2. Match when_asked conditions against assistant text
        norm_text = (assistant_text or "").lower()
        for idx, step in enumerate(self.script.script):
            if idx in self._matched_steps:
                continue
            if step.when_asked:
                keywords = self.ASKED_KEYWORDS.get(step.when_asked, [step.when_asked])
                if any(kw in norm_text for kw in keywords):
                    self._matched_steps.add(idx)
                    return step.say, step.do, None

        # 3. Match any unused unconditional say step
        for idx, step in enumerate(self.script.script):
            if idx in self._matched_steps:
                continue
            if step.say and not step.when_asked and not step.on_proposal:
                self._matched_steps.add(idx)
                return step.say, step.do, None

        # 4. Fallback if no matching step
        self.fallback_turns += 1
        return self.script.fallback_say, None, None
